"""Independent optional workstation tab; no controller/recorder lifecycle changes."""
import queue,threading,webbrowser
import tkinter as tk
from tkinter import ttk
from offline_replay.launcher import launch
class ReplayPanel(ttk.Frame):
    def __init__(self,parent,config):
        super().__init__(parent,padding=22);self.config_fn=config;self.handle=None;self.events=queue.Queue();self.entries={};self.busy=False
        ttk.Label(self,text='G1 + Dex1 · 离线 3D 回放',font=('Noto Sans CJK SC',21,'bold')).pack(anchor='w')
        ttk.Label(self,text='真实关节反馈 · 统一视频时间轴 · 独立低优先级显示进程').pack(anchor='w',pady=(6,18))
        ttk.Label(self,text='固定基座，不代表全局行走轨迹。机器人可以关机；本页不启动 SONIC、PICO 或电机控制。',wraplength=950).pack(anchor='w',pady=(0,18))
        self.selected=tk.StringVar();self.combo=ttk.Combobox(self,textvariable=self.selected,state='readonly',width=80);self.combo.pack(anchor='w',fill='x')
        row=ttk.Frame(self);row.pack(anchor='w',pady=16)
        for text,fn in [('刷新已保存片段',self.refresh),('打开独立 3D 回放',self.open),('关闭 3D 显示进程',self.stop)]:ttk.Button(row,text=text,command=fn).pack(side='left',padx=(0,12))
        self.status=tk.StringVar(value='尚未启动 3D 显示；原数采和遥操功能不受影响。');ttk.Label(self,textvariable=self.status,wraplength=1000).pack(anchor='w',pady=(0,16))
        ttk.Label(self,text='数据说明\n\n• 实际姿态：observation.body / 原始 g1_debug.body_q，29 个关节，单位 rad。\n• 目标姿态：action.body / 已缩放的 SONIC last_action，单独切换显示。\n• Dex1：保留物理左右各1D原始电机弧度；只为显示映射为四个滑动关节。\n• 人体姿态与64D latent token均不当作机器人关节角。\n• 支持播放/暂停、0.25–4倍速、拖动时间轴、视角调节和关节曲线。\n• 关闭或崩溃只结束此显示进程，不停止数采，也不向真机回写。',justify='left',wraplength=1000).pack(anchor='w')
        self.refresh();self.after(200,self.poll);self.bind('<Destroy>',self.cleanup,add='+')
    def refresh(self):
        from official_sonic.console.data_manager import rows
        self.entries={f"第 {r['number']} 段 · {r['task']} · {r['frames']}帧 · {r['batch']}":r['episode'] for r in rows(self.config_fn())}
        self.combo['values']=list(self.entries)
        if self.selected.get() not in self.entries:self.selected.set(next(reversed(self.entries),'') if self.entries else '')
    def open(self):
        if self.busy:return
        if self.handle and self.handle.process.poll() is None:self.status.set('已有独立3D回放进程；先关闭它再切换片段。');return
        episode=self.entries.get(self.selected.get())
        if not episode:self.status.set('没有可用片段，请先录制并完整保存。');return
        self.busy=True;self.status.set('正在验证记录和加载独立被动模型……')
        def work():
            try:
                h=launch(episode);self.events.put(('started',h));ready=h.wait_ready();self.events.put(('ready',ready))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=work,daemon=True).start()
    def stop(self):
        if not self.handle:return
        h=self.handle
        def work():h.stop();self.events.put(('stopped',None))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='started':self.handle=value
                elif kind=='ready':self.busy=False;self.status.set('离线3D已启动 · '+value['url']+' · '+value['renderer']);webbrowser.open(value['url'])
                elif kind=='error':self.busy=False;self.status.set(value)
                elif kind=='stopped':self.busy=False;self.status.set('3D显示进程已关闭；未改变数采或控制状态。')
        except queue.Empty:pass
        if self.handle and self.handle.process.poll() is not None and not self.busy:self.status.set('3D进程已结束；可重新打开。数采独立运行。')
        self.after(200,self.poll)
    def cleanup(self,event):
        if event.widget is self and self.handle:
            if self.handle.process.poll() is None:self.handle.process.terminate()
