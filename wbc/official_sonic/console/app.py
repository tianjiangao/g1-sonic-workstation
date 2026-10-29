#!/usr/bin/env python3
"""Local SONIC console with passive preview and Dex1 data adapters."""
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tempfile
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from official_sonic.console.backend import BASE, BLOCKERS, Config, ConfigStore, JobManager, commands, local_status, preview, capture_command, recording_request
from official_sonic.console.camera_autostart import preview_note
from official_sonic.console import data_manager
from official_sonic.console.episode_panel import EpisodePanel
from offline_replay.panel import ReplayPanel
from official_sonic.console.ssh_connection import connect as connect_robot

class Console:
    def __init__(self,root,store=None):
        global Image,ImageTk
        from PIL import Image,ImageTk
        self.root=root;self.store=store or ConfigStore();self.events=queue.Queue();self.closing=False;self.stopping=False
        self.jobs=JobManager(BASE/'logs',commands());self.error=None;self.last_log=''
        try:config=self.store.load()
        except ValueError as e:config=Config();self.error=str(e)
        root.title('SONIC 工作站');root.geometry('1380x970');root.minsize(1120,860);root.configure(bg='#f5f7fa');root.attributes('-zoomed',True)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',font=('Noto Sans CJK SC',11),background='#f5f7fa',foreground='#172b40')
        style.configure('TButton',padding=(16,11),background='#ffffff',borderwidth=1)
        style.configure('Primary.TButton',background='#0f766e',foreground='#ffffff',font=('Noto Sans CJK SC',12,'bold'))
        style.map('Primary.TButton',background=[('active','#115e59'),('disabled','#ccd7db')],foreground=[('disabled','#586973')])
        style.configure('TNotebook.Tab',padding=(18,10));style.configure('TEntry',padding=6)
        style.configure('Treeview',rowheight=34,font=('Noto Sans CJK SC',10),background='white',fieldbackground='white')
        style.configure('Treeview.Heading',font=('Noto Sans CJK SC',10,'bold'),padding=7)
        style.configure('Title.TLabel',font=('Noto Sans CJK SC',25,'bold'))
        style.configure('Note.TLabel',foreground='#815714')
        outer=ttk.Frame(root,padding=22);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='SONIC 工作站',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='TELEOPERATION  /  DATA COLLECTION    ·    三路视觉 · SONIC · Dex1').pack(anchor='w',pady=(2,12))
        self.banner=ttk.Label(outer,text='正在自动连接 G1……连接后显示三路图像；遥操仍需现场确认。',style='Note.TLabel')
        self.banner.pack(anchor='w',pady=(0,12))
        notebook=ttk.Notebook(outer);notebook.pack(fill='both',expand=True);self.notebook=notebook
        work=ttk.Frame(notebook,padding=14);settings=ttk.Frame(notebook,padding=18);logs=ttk.Frame(notebook,padding=12)
        hardware=ttk.Frame(notebook,padding=16)
        notebook.add(work,text='  采集工作台  ');self.library=EpisodePanel(notebook,self.store.load);notebook.add(self.library,text='  片段与回放  ');self.replay3d=ReplayPanel(notebook,self.store.load);notebook.add(self.replay3d,text='  3D / 回放  ');notebook.add(hardware,text='  机器人设备  ');notebook.add(settings,text='  采集设置  ');notebook.add(logs,text='  运行日志  ')
        self.record_state=tk.StringVar(value='等待数采连接')
        self.startup_note=tk.StringVar(value='启动状态：尚未启控；启动前检查不会进入INIT或IDLE')
        self.startup_label=ttk.Label(work,textvariable=self.startup_note,wraplength=1020,style='Note.TLabel')
        self.startup_label.pack(anchor='w',pady=(0,8))
        ttk.Label(work,textvariable=self.record_state,font=('Noto Sans CJK SC',19,'bold')).pack(anchor='w',pady=(0,8))
        metrics=ttk.Frame(work);metrics.pack(fill='x',pady=(0,12));self.metrics={}
        for key,label in [('take','当前片段'),('duration','录制时长'),('frames','有效帧数'),('saved','本次已保存')]:
            panel=ttk.Frame(metrics,padding=(12,3));panel.pack(side='left',fill='x',expand=True)
            ttk.Label(panel,text=label).pack(anchor='w')
            self.metrics[key]=tk.StringVar(value='—')
            ttk.Label(panel,textvariable=self.metrics[key],font=('DejaVu Sans',21,'bold')).pack(anchor='w')
        cameras=ttk.Frame(work);self.camera_frame=cameras;cameras.pack(fill='x',pady=(0,12));self.camera_widgets={};self.camera_photos={};self.camera_times={}
        for i,(role,label) in enumerate([('camera_head','头部 · 双目'),('camera_left','左腕'),('camera_right','右腕')]):
            cameras.columnconfigure(i,weight=2 if i==0 else 1,uniform='camera')
            pane=ttk.Frame(cameras,padding=(4,0));pane.grid(row=0,column=i,sticky='nsew')
            ttk.Label(pane,text=label,font=('Noto Sans CJK SC',12,'bold')).pack(anchor='w')
            viewport=ttk.Frame(pane,height=200);viewport.pack(fill='x');viewport.pack_propagate(False)
            image=tk.Label(viewport,text='等待 SONIC 相机流',bg='#f5f7fa',fg='#172b40',borderwidth=0,highlightthickness=0)
            image.place(x=0,y=0,relwidth=1,relheight=1)
            note=tk.StringVar(value=preview_note(None,time.time()))
            ttk.Label(pane,textvariable=note).pack(anchor='w');self.camera_widgets[role]=(image,note)
        self.dex_note=tk.StringVar(value='夹爪：等待实时反馈；发送指令不代表已夹取')
        ttk.Label(work,textvariable=self.dex_note,wraplength=1200).pack(anchor='w',pady=(0,5))
        self.table=ttk.Treeview(hardware,columns=('component','state','detail'),show='headings',height=8,selectmode='none')
        for name,label,width in [('component','组件',150),('state','状态',90),('detail','说明',665)]:
            self.table.heading(name,text=label);self.table.column(name,width=width,minwidth=width if name!='detail' else 400,stretch=name=='detail')
        self.table.pack(fill='x',pady=(0,12))
        row=ttk.Frame(settings);row.grid(row=12,column=0,columnspan=3,sticky='w',pady=(15,7));self.action_buttons=[]
        for title,name in [('启动前检查','prepare'),('启动 PICO PC Service','service'),('采集组件自检','check'),('检查 PICO 数据','pico'),('隔离仿真','sim'),('离线仿真自检','offline')]:
            b=ttk.Button(row,text=title,command=lambda n=name:self.start(n));b.pack(side='left',padx=(0,8));self.action_buttons.append(b)
        row=ttk.Frame(work);row.pack(fill='x',pady=5)
        ttk.Button(row,text='刷新本机状态',command=self.refresh).pack(side='left',padx=(0,8))
        self.stop_button=ttk.Button(row,text='停止本次作业',command=self.stop,state='disabled');self.stop_button.pack(side='left',padx=(0,8))
        ttk.Button(row,text='查看官方流程',command=lambda:self.open_path(ROOT/'official_sonic/README.zh-CN.md')).pack(side='left')
        self.real_button=ttk.Button(work,text='启动遥操与数采（启动后需点开始采集）',command=self.start_real,style='Primary.TButton');self.real_button.pack(anchor='w',pady=(12,4))
        self.action_buttons.append(self.real_button)
        row=ttk.Frame(work);row.pack(fill='x',pady=5);self.record_buttons={}
        for title,callback in [('仅启动数采（遥操已运行）',lambda:self.start('capture')),('开始采集',lambda:self.record('start')),('结束并保存',lambda:self.record('stop')),('导出最近保存段',lambda:self.start('export')),('测试机器人播报',lambda:self.start('voice'))]:
            button=ttk.Button(row,text=title,command=callback);button.pack(side='left',padx=(0,8))
            if title in ('开始采集','结束并保存'):self.record_buttons[title]=button
            else:self.action_buttons.append(button)
        self.batch_note=tk.StringVar()
        ttk.Label(work,textvariable=self.batch_note,font=('Noto Sans CJK SC',12,'bold')).pack(anchor='w',pady=(12,5))
        self.batch_button=ttk.Button(work,text='结束本批次 · 下次从第 1 段开始',command=self.finish_batch)
        self.batch_button.pack(anchor='w',pady=(0,8))
        self.capture_note=tk.StringVar(value='数采未运行。默认15Hz，保存三路图像、身体和左右夹爪状态/命令。')
        ttk.Label(work,textvariable=self.capture_note,wraplength=920,style='Note.TLabel').pack(anchor='w')
        ttk.Label(work,text='停止按钮只管理本控制台启动的作业，不能代替真实机器人急停。').pack(anchor='w',pady=(5,0))
        ttk.Label(hardware,text='机器人只读检查',font=('Noto Sans CJK SC',16,'bold')).pack(anchor='w')
        ttk.Label(hardware,text='显式点击后通过 SSH 枚举 USB、相机和进程；不启动相机流、不发送控制指令。',wraplength=940).pack(anchor='w',pady=10)
        b=ttk.Button(hardware,text='检查 Orin 设备与控制器',command=lambda:self.start('inventory'))
        b.pack(anchor='w');self.action_buttons.append(b)
        b=ttk.Button(hardware,text='检查/启动 SONIC 三路相机',command=lambda:self.start('camera'))
        b.pack(anchor='w',pady=(8,0));self.action_buttons.append(b)
        self.hardware_note=tk.StringVar(value='尚未检查。历史检查不能代表当前设备状态。')
        ttk.Label(hardware,textvariable=self.hardware_note,wraplength=940,style='Note.TLabel').pack(anchor='w',pady=12)
        self.hardware_text=tk.Text(hardware,height=17,wrap='word',bg='white',fg='#172b40',font=('Noto Sans CJK SC',11),state='disabled')
        self.hardware_text.pack(fill='both',expand=True)
        ttk.Button(hardware,text='打开最近检查原始记录',command=lambda:self.open_path(BASE/'remote-inventory.json')).pack(anchor='w',pady=10)
        self.last_inventory=''
        self.vars={};labels={'robot_ip':'机器人 Orin IP','camera_ip':'相机服务器 IP','streamer_ip':'PICO 发布主机 IP',
            'task':'本次任务描述','dataset':'数据集名称','output':'真实采集保存目录','frequency':'采集频率 / Hz'}
        settings.columnconfigure(1,weight=1)
        for i,(key,value) in enumerate(asdict(config).items()):
            ttk.Label(settings,text=labels[key]).grid(row=i,column=0,sticky='w',padx=(0,18),pady=9)
            var=tk.StringVar(value=str(value));self.vars[key]=var
            ttk.Entry(settings,textvariable=var).grid(row=i,column=1,sticky='ew',pady=9)
            if key=='output':ttk.Button(settings,text='选择目录',command=self.choose_output).grid(row=i,column=2,padx=(8,0))
        row=ttk.Frame(settings);row.grid(row=8,column=0,columnspan=3,sticky='w',pady=18)
        ttk.Button(row,text='保存设置',command=self.save).pack(side='left',padx=(0,10))
        ttk.Button(row,text='预览当前采集参数',command=self.show_preview).pack(side='left',padx=(0,10))
        ttk.Button(row,text='打开数据目录',command=self.open_output).pack(side='left')
        ttk.Label(settings,text='设置保存前自动备份。参数预览不会启动采集器，也不会发送机器人命令。',wraplength=760).grid(row=9,column=0,columnspan=3,sticky='w')
        ttk.Label(settings,text='自检生成的数据单独标注 SYNTHETIC_ONLY，不进入真实采集保存目录。',wraplength=760).grid(row=10,column=0,columnspan=3,sticky='w',pady=10)
        scroll=ttk.Scrollbar(logs);scroll.pack(side='right',fill='y')
        self.log_text=tk.Text(logs,wrap='word',font=('DejaVu Sans Mono',10),bg='#ffffff',fg='#172b40',yscrollcommand=scroll.set,state='disabled')
        self.log_text.pack(fill='both',expand=True);scroll.configure(command=self.log_text.yview)
        row=ttk.Frame(logs);row.pack(fill='x',pady=(10,0))
        ttk.Button(row,text='打开本次日志目录',command=self.open_logs).pack(side='left',padx=(0,10))
        ttk.Button(row,text='打开自检数据目录',command=lambda:self.open_path(BASE/'selftests')).pack(side='left')
        self.footer=tk.StringVar(value=self.error or '就绪。尚未启动任何作业。')
        ttk.Label(outer,textvariable=self.footer,wraplength=1000).pack(anchor='w',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.preview_cache=Path(tempfile.mkdtemp(prefix='sonic-preview-'))
        env=dict(__import__('os').environ,PYTHONPATH='/opt/g1/workspace')
        self.preview_log_path=BASE/'logs'/('preview-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.log')
        self.preview_log_path.parent.mkdir(parents=True,exist_ok=True)
        self.preview_log=self.preview_log_path.open('ab')
        self.preview_process=subprocess.Popen([str(ROOT/'.venv_sim/bin/python'),'-m','capture.live_view','--host',config.camera_ip,'--cache',str(self.preview_cache)],env=env,stdout=self.preview_log,stderr=self.preview_log)
        self.preview_after=None
        root.bind('<Destroy>',self.cleanup_preview,add='+')
        self.ssh_busy=False
        self.refresh();self.update_cameras();self.poll();self.check_ssh()
    def check_ssh(self):
        if self.closing:return
        self.root.after(30000,self.check_ssh)
        if self.ssh_busy:return
        try:host=self.config().robot_ip
        except ValueError as e:
            self.banner.configure(text='SSH未连接：'+str(e));return
        self.ssh_busy=True
        def work():
            try:
                result=connect_robot(host)
                text='G1 SSH 已连接 · '+result['host']+' · 遥操仍需现场确认，数据就绪后开始录制。'
            except (OSError,ValueError,RuntimeError):text='机器人离线或SSH未连接 · 离线质检和回放仍可使用；30秒后重试。'
            self.events.put(('ssh',text))
        threading.Thread(target=work,daemon=True).start()
    def config(self):
        values={k:v.get() for k,v in self.vars.items()};values['frequency']=int(values['frequency'])
        return Config(**values).validate()
    def save(self):
        try:
            self.store.save(self.config());self.error=None;self.footer.set('设置已保存；之前的版本已备份。')
        except ValueError as e:messagebox.showerror('设置未保存',str(e),parent=self.root)
    def choose_output(self):
        path=filedialog.askdirectory(parent=self.root)
        if path:self.vars['output'].set(path)
    def open_output(self):
        try:
            path=Path(self.config().output);path.mkdir(parents=True,exist_ok=True);self.open_path(path)
        except (OSError,ValueError) as e:messagebox.showerror('无法打开',str(e),parent=self.root)
    def open_logs(self):self.open_path(self.jobs.log.parent if self.jobs.log else BASE/'logs')
    def open_path(self,path):
        if not Path(path).exists():self.footer.set('此目录尚未生成：'+str(path));return
        subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def show_preview(self):
        try:
            p=BASE/'launch-plan.json';p.write_text(json.dumps(preview(self.config()),ensure_ascii=False,indent=2))
            self.footer.set('已保存参数预览：'+str(p));self.open_path(p)
        except ValueError as e:messagebox.showerror('参数无效',str(e),parent=self.root)
    def refresh(self):
        def work():
            try:self.events.put(('status',local_status()))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()
    def start(self,name):
        try:
            if self.error:raise ValueError(self.error+'；请先修复并保存设置')
            config=self.config()
            if name in ('inventory','camera','real','capture','prepare','export'):self.store.save(config)
            if name=='capture':self.jobs.allowed['capture']=capture_command(config)
            self.jobs.start(name);self.last_log='';self.footer.set('作业运行中：'+name+'；详见运行日志。')
        except (ValueError,RuntimeError,OSError) as e:messagebox.showerror('未启动',str(e),parent=self.root)
    def start_real(self):
        if self.jobs.running():return
        if not messagebox.askyesno('开始真实机器人验证',
            '将释放机载 ai 运控，确认原命令停止后启动原版 SONIC；INIT 会带力。Dex1 在收到新鲜数据后响应扳机。\n\n'
            '确认机器人可靠悬挂/支撑、旁站持独立急停、双手远离夹爪？\n'
            '左扳机→左夹爪，右扳机→右夹爪；按下闭合、激活后松开回到官方最大开度。首次轻按。\n\n'
            'SONIC进入控制且扳机松开后，两夹爪会自动缓慢打开到最大开度，请保持夹爪行程内无人无物。\n\n'
            '会准备缺失的运行容器并启动Dex1服务（包含串口探测），然后启动遥操和数采。\n录制通过界面按钮或现有PICO录制快捷键操作。',parent=self.root):return
        self.start('real')
        self.notebook.select(0)
    def record(self,action):
        if not self.jobs.running() or self.jobs.name not in ('real','capture'):
            messagebox.showinfo('数采未运行','请先启动遥操与数采，或仅启动数采。',parent=self.root);return
        recording_request(action)
        self.footer.set('已请求'+('开始采集' if action=='start' else '结束并保存')+'；实际开始/保存后会播报并更新状态。')

    def finish_batch(self):
        if not messagebox.askyesno('结束本批次','当前录制中的片段将结束并保存；下一次从第1段计数。历史片段全部保留。此操作不会停止机器人遥操，也不能代替急停。',parent=self.root):return
        try:
            if self.jobs.running():
                if self.jobs.name not in ('real','capture'):raise RuntimeError('请先等待当前作业结束')
                recording_request('finish_batch');self.footer.set('已请求结束并保存当前片段，然后开启新批次。')
            else:
                data_manager.finish_idle(self.config());self.library.refresh();self.footer.set('本批次已结束；下一次从第1段开始，历史片段保留。')
        except (OSError,RuntimeError,ValueError) as e:messagebox.showerror('批次未结束',str(e),parent=self.root)

    def stop(self):
        if self.stopping:return
        self.stopping=True;self.footer.set('正在停止本控制台的作业并等待清理……')
        def work():
            try:self.jobs.stop();self.events.put(('stopped',None))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='status':
                    for item in self.table.get_children():self.table.delete(item)
                    for row in value:self.table.insert('',tk.END,values=row)
                elif kind=='error':self.stopping=False;self.closing=False;self.footer.set('失败：'+value)
                elif kind=='ssh':
                    self.ssh_busy=False;self.banner.configure(text=value)
                elif kind=='stopped':
                    self.stopping=False;self.footer.set('本次作业已停止。')
                    if self.closing:self.root.destroy();return
        except queue.Empty:pass
        state=self.jobs.snapshot();busy=state['running'] or self.stopping
        try:
            startup=json.loads((BASE/'startup-status.json').read_text())
            if state['running'] and state['name']=='real' and startup.get('pid')==state['pid'] and time.time()-startup.get('time_epoch',0)<3:
                text='启动阶段：'+startup['phase']+' · '+startup['note']
                if startup.get('alert'):text+='\n'+startup['alert']
                self.startup_label.configure(foreground='#b42318' if startup.get('alert') else '#815714')
                thermal=startup.get('thermal')
                if thermal and thermal.get('available'):
                    text+='\n踝关节温度：'+' · '.join(x['name']+f" {x['peak_C']:.0f}°C" for x in thermal['ankles'])+'（电机上报值）'
                self.startup_note.set(text)
            elif state['running'] and state['name']=='prepare':self.startup_note.set('启动前检查进行中；不进入INIT、不进入IDLE、不解除热异常拦截')
        except (OSError,ValueError,KeyError):pass
        try:
            hold=json.loads((ROOT/'official_sonic/health_hold.json').read_text())
            if hold.get('blocked') and not state['running']:self.startup_note.set('热安全暂缓：右踝异常未验收，新真机会话不会启动。可运行启动前检查。')
        except (OSError,ValueError):pass
        can_start=False;can_stop=False
        try:
            batch=data_manager.state(data_manager.dataset_root(self.store.load()))
            self.batch_note.set(f"当前批次 {batch['batch_id']}   ·   下段编号 {batch['last_number']+1}   ·   历史保留 {len(self.library.entries)} 段")
        except (OSError,ValueError):batch=None
        try:
            sessions=sorted((Path(self.store.load().output)/self.store.load().dataset).glob('SESSION_*/status.json'))
            if sessions:
                path=sessions[-1];capture=json.loads(path.read_text())
                age=time.time()-path.stat().st_mtime
                text=('录制中' if capture['recording'] else ('数据就绪，可开始录制' if capture['ready'] else '等待数据：'+str(capture['blocked_reason'])))
                if age>5:text='数采未运行 · 历史片段见「片段与回放」'
                if age>5 and batch and batch['batch_id']!=capture.get('batch_id','legacy'):
                    capture=dict(capture,take_number=None,duration_s=0.,frames=0,saved_episodes=0,last_event=None)
                    text='新批次已就绪 · 等待开始数采'
                frames=capture.get('frames')
                if frames is None and capture.get('last_saved_path'):
                    try:frames=json.loads((Path(capture['last_saved_path'])/'episode.json').read_text()).get('frames')
                    except (OSError,ValueError):pass
                can_start=age<5 and capture['ready'] and not capture['recording'] and state['running'] and state['name'] in ('real','capture')
                can_stop=age<5 and capture['recording'] and state['running'] and state['name'] in ('real','capture')
                saved=capture.get('saved_episodes',0);number=capture.get('take_number')
                event=(capture.get('last_event') or {}).get('text','')
                if age<5:
                    ages=capture.get('ages_s',{})
                    groups=[('身体',['g1_debug']),('三路相机',['camera_head','camera_left','camera_right']),('左右夹爪命令',['dex1_left_cmd','dex1_right_cmd'])]
                    health=[]
                    for label,keys in groups:
                        health.append(label+(' '+f'{max(ages[k] for k in keys)*1000:.0f}ms' if all(k in ages for k in keys) else ' 待接入'))
                    event+='\n必要流接收年龄：'+' · '.join(health)+'（非曝光时钟同步）'
                saved_path=capture.get('last_saved_path')
                if saved_path and saved_path!=getattr(self,'library_last_saved',None) and self.notebook.index('current')!=1:
                    self.library_last_saved=saved_path;self.library.refresh()
                self.record_state.set(text)
                for key,value in [('take',str(number) if number else '—'),('duration',f"{capture['duration_s']:.1f} 秒" if 'duration_s' in capture else '—'),('frames',str(frames) if frames is not None else '—'),('saved',f'{saved} 条')]:self.metrics[key].set(value)
                self.capture_note.set((text+' · 下一段从第1段开始，历史片段已保留。') if age>5 and batch and batch['batch_id']!=capture.get('batch_id','legacy') else text+f' · 本次已保存{saved}条'+(f' · 当前第{number}条' if number else '')+'\n'+event)
        except (OSError,ValueError,KeyError):pass
        self.record_buttons['开始采集'].configure(state='normal' if can_start else 'disabled')
        self.record_buttons['结束并保存'].configure(state='normal' if can_stop else 'disabled')
        inventory=BASE/'remote-inventory.json'
        if inventory.exists():
            try:
                raw=inventory.read_text();d=json.loads(raw)
                age=(datetime.now().astimezone()-datetime.fromisoformat(d['observed_at'])).total_seconds()
                self.hardware_note.set(f"检查时间：{d['observed_at']} · {int(max(0,age))} 秒前 · "+('仅供历史参考，请重新检查' if age>30 else '只读枚举结果，不是控制验收'))
                if raw!=self.last_inventory:
                    if 'inventory' in d:
                        inv=d['inventory'];summary=d['summary']
                        cameras='\n'.join('  '+v['name']+' / '+v['serial'] for v in inv.get('camera_devices',[])) or '  未识别到相机'
                        roles=ROOT/'official_sonic/profiles/camera-roles.json'
                        role_text='未确认'
                        if roles.exists():
                            mapping=json.loads(roles.read_text());role_text='\n'.join(f"  {k}: {v.get('serial') or '未知'} / {'已确认' if v.get('confirmed') else '待确认'}" for k,v in mapping.items() if isinstance(v,dict))
                        text=f"相机设备（SDK 枚举）\n{cameras}\n\n角色映射\n{role_text}\n\n控制器进程：{summary['controller_count']}\n自动启动服务：{summary['autostart']}\n\n未完成项\n"+'\n'.join('  '+x for x in summary['blockers'])
                    else:text='未取得机器人清单：'+d.get('error','未知错误')+'\n'+d.get('hint','')
                    self.hardware_text.configure(state='normal');self.hardware_text.delete('1.0',tk.END);self.hardware_text.insert(tk.END,text);self.hardware_text.configure(state='disabled');self.last_inventory=raw
            except (OSError,ValueError,KeyError):pass
        for b in self.action_buttons:b.configure(state='disabled' if busy or self.error else 'normal')
        self.stop_button.configure(state='normal' if state['running'] and not self.stopping else 'disabled')
        if self.jobs.log:
            try:
                with self.jobs.log.open('rb') as f:
                    f.seek(max(0,self.jobs.log.stat().st_size-24000));data=f.read().decode(errors='replace')
                if data!=self.last_log:
                    self.log_text.configure(state='normal');self.log_text.delete('1.0',tk.END);self.log_text.insert(tk.END,data)
                    self.log_text.see(tk.END);self.log_text.configure(state='disabled');self.last_log=data
                if not busy:self.footer.set(f"最近作业 {state['name']}：退出码 {state['returncode']}。日志：{self.jobs.log.parent.name}")
            except OSError:pass
        self.root.after(400,self.poll)
    def update_cameras(self):
        try:
            status=json.loads((self.preview_cache/'status.json').read_text())
            for role,(widget,note) in self.camera_widgets.items():
                info=status.get('cameras',{}).get(role)
                if not info:continue
                age=time.time()-info['received_at'];path=self.preview_cache/(role+'.jpg')
                width=max(2,widget.master.winfo_width());height=min(290,max(2,round(width*info['shape'][0]/info['shape'][1])))
                widget.master.configure(height=height)
                stamp=(path.stat().st_mtime_ns,width,height)
                if self.camera_times.get(role)!=stamp:
                    with Image.open(path) as src:
                        from PIL import ImageOps
                        photo=ImageTk.PhotoImage(ImageOps.contain(src,(width,height),getattr(Image,'Resampling',Image).LANCZOS))
                    self.camera_photos[role]=photo;widget.configure(image=photo,text='');self.camera_times[role]=stamp
                note.set(preview_note(info,time.time(),status.get('average_fps',0)))
                if age>=1 or age<0:widget.configure(image='',text='相机断流 · 等待恢复')
        except (OSError,ValueError,KeyError):pass
        if self.preview_process.poll() is not None:
            for widget,note in self.camera_widgets.values():
                widget.configure(image='',text='预览进程已退出')
                note.set('预览失败；日志：'+str(self.preview_log_path))
        try:
            paths=sorted((ROOT/'official_sonic/real_sessions').glob('*/dex1.json'))
            if paths:
                path=paths[-1];d=json.loads(path.read_text());age=time.time()-path.stat().st_mtime
                if age<1:
                    parts=[]
                    for side,label in [('left','左'),('right','右')]:
                        q=d.get('state',{}).get(side,{}).get('q');cmd=d.get('last_command',{}).get(side,{}).get('q');trigger=(d.get('trigger') or {}).get(side,0)
                        parts.append(f'{label}扳机 {trigger:.0%} / '+(f'位置 {q:.3f} → 指令 {cmd:.3f} rad' if q is not None and cmd is not None else '等待反馈'))
                    self.dex_note.set('夹爪 '+d.get('result','')+' · '+'  |  '.join(parts))
                else:self.dex_note.set('夹爪：当前没有新鲜的遥操反馈；上次会话状态不代表现在可用')
        except (OSError,ValueError,KeyError):pass
        self.preview_after=self.root.after(200,self.update_cameras)
    def cleanup_preview(self,event):
        if event.widget is not self.root:return
        if self.preview_process.poll() is None:
            self.preview_process.terminate()
            self.preview_process.wait(timeout=5)
        self.preview_log.close()
        import shutil
        shutil.rmtree(self.preview_cache,ignore_errors=True)
    def close(self):
        if self.jobs.running():self.closing=True;self.stop()
        else:self.root.destroy()

def main():
    BASE.mkdir(parents=True,exist_ok=True)
    lock=(BASE/'console.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        subprocess.run(['zenity','--info','--text=SONIC 控制台已在运行，请从任务栏打开。']);return
    root=tk.Tk(className='SonicWorkstation');Console(root);root.mainloop()

if __name__=='__main__':main()
