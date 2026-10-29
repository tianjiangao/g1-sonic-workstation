"""Native offline episode library and human labels; never starts robot jobs."""
import json,queue,threading,webbrowser
import tkinter as tk
from tkinter import ttk,messagebox
from official_sonic.console import data_manager as data

LABELS={'pending':'待审核','success':'人工成功','failed':'人工失败','device_test':'设备测试'}
class EpisodePanel(ttk.Frame):
    def __init__(self,parent,config):
        super().__init__(parent,padding=18);self.config_fn=config;self.events=queue.Queue();self.entries={}
        ttk.Label(self,text='采集片段',style='Title.TLabel').pack(anchor='w')
        self.summary=tk.StringVar();ttk.Label(self,textvariable=self.summary).pack(anchor='w',pady=(6,14))
        self.table=ttk.Treeview(self,columns=('batch','number','task','duration','frames','decision'),show='headings',height=8)
        for name,title,width in [('batch','批次',180),('number','段号',65),('task','任务',250),('duration','时长',90),('frames','帧数',80),('decision','人工状态',130)]:
            self.table.heading(name,text=title);self.table.column(name,width=width,stretch=name=='task')
        self.table.pack(fill='x');self.table.bind('<<TreeviewSelect>>',self.select)
        actions=ttk.Frame(self);actions.pack(fill='x',pady=12)
        for label,fn in [('刷新片段',self.refresh),('离线质检',self.check),('三路回放',self.replay)]:ttk.Button(actions,text=label,command=fn).pack(side='left',padx=(0,10))
        ttk.Label(self,text='接收年龄 ≠ 传感器曝光同步；结构质检通过 ≠ 任务成功或训练验收。',style='Note.TLabel').pack(anchor='w',pady=(0,12))
        form=ttk.Frame(self);form.pack(fill='x');self.decision=tk.StringVar(value='待审核');self.reviewer=tk.StringVar();self.note=tk.StringVar()
        ttk.Label(form,text='人工标签').pack(side='left');ttk.Combobox(form,textvariable=self.decision,values=list(LABELS.values()),state='readonly',width=12).pack(side='left',padx=8)
        ttk.Label(form,text='审核人').pack(side='left');ttk.Entry(form,textvariable=self.reviewer,width=14).pack(side='left',padx=8)
        ttk.Label(form,text='依据 / 失败原因').pack(side='left');ttk.Entry(form,textvariable=self.note,width=34).pack(side='left',padx=8,fill='x',expand=True)
        ttk.Button(form,text='保存人工标签',command=self.annotate).pack(side='left')
        ttk.Label(self,text='标签仅用于本机整理；正式 approved、整 session 划分、清洗和读取器验收仍走原流程。').pack(anchor='w',pady=8)
        self.detail=tk.Text(self,height=13,wrap='word',font=('DejaVu Sans Mono',10),bg='#ffffff',fg='#243746',relief='flat',padx=16,pady=12)
        self.detail.pack(fill='both',expand=True);self.refresh();self.after(150,self.poll)
    def refresh(self):
        selected=self.table.selection();rows=data.rows(self.config_fn());self.entries={r['id']:r for r in rows}
        self.table.delete(*self.table.get_children())
        for row in rows:self.table.insert('',tk.END,iid=row['id'],values=(row['batch'],row['number'],row['task'],f"{row['duration_s']:.1f}s",row['frames'],LABELS.get(row['decision'],row['decision'])))
        total=len(rows);success=sum(r['decision']=='success' for r in rows);failed=sum(r['decision']=='failed' for r in rows);reviewed=success+failed
        self.summary.set(f'保留 {total} 段  ·  待审核 {sum(r["decision"]=="pending" for r in rows)} 段  ·  人工成功率 '+(f'{success/reviewed:.0%}（{reviewed}段已评估）' if reviewed else '尚未评估'))
        if selected and selected[0] in self.entries:self.table.selection_set(selected[0])
    def chosen(self):
        selection=self.table.selection()
        if not selection:raise ValueError('请先选择一个片段')
        return self.entries[selection[0]]
    def show(self,text):self.detail.delete('1.0',tk.END);self.detail.insert('1.0',text)
    def select(self,event=None):
        try:
            r=self.chosen();self.decision.set(LABELS[r['decision']]);self.reviewer.set(r.get('reviewer',''));self.note.set(r.get('note',''))
            self.show(f"{r['task']}\n批次 {r['batch']} / 第 {r['number']} 段\n{r['episode']}\n\n点击离线质检查看身体与夹爪动作入库、64D token、接收年龄和相机帧证据；点击三路回放进行人工审核。")
        except ValueError:pass
    def worker(self,fn):
        try:r=self.chosen()
        except ValueError as e:messagebox.showinfo('片段管理',str(e),parent=self);return
        self.show('正在读取本机已保存数据……不连接机器人。')
        def work():
            try:self.events.put(('result',fn(r)))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()
    def check(self):self.worker(data.check)
    def replay(self):self.worker(data.replay)
    def annotate(self):
        try:data.annotate(self.chosen(),{v:k for k,v in LABELS.items()}[self.decision.get()],self.reviewer.get(),self.note.get());self.refresh();self.show('人工标签已保存。正式训练审批未改变。')
        except (ValueError,OSError) as e:messagebox.showerror('未保存',str(e),parent=self)
    def poll(self):
        try:
            while True:
                kind,result=self.events.get_nowait()
                if kind=='result' and result.get('schema')=='workstation-quality-v1':
                    lines=['离线结构质检：'+('通过（非训练验收）' if result['result']=='PASS_STRUCTURAL' else '失败'),
                        f"{result['frames']} 帧 · {result['duration_s']:.1f} 秒 · 有效64D token事件 {result['valid_64d_token_events']}",
                        '\n工作站接收年龄       P95 / 最大（ms）']
                    for stream,stat in result['receipt_age'].items():lines.append(f"{stream:22} {stat['p95_ms']:7.1f} / {stat['max_ms']:7.1f}")
                    lines+=['\nDex1状态／命令范围（rad）',json.dumps(result['dex1_ranges'],ensure_ascii=False),'\n问题：'+('；'.join(result['errors']) or '未发现结构性缺失'),'\n提醒：'+('；'.join(result.get('warnings',[])) or '无额外结构提醒'),'\n人工审核：待定；传感器曝光时钟未证明同步；正式清洗和读取器验收尚未执行。']
                    self.show('\n'.join(lines))
                else:self.show(json.dumps(result,ensure_ascii=False,indent=2) if kind=='result' else '失败：'+result)
                if kind=='result' and 'url' in result:webbrowser.open(result['url'])
        except queue.Empty:pass
        self.after(150,self.poll)
