# tmux 使用备忘

tmux 是终端复用器，主要用来让命令行任务在后台继续跑。尤其适合 SSH 远程服务器、长时间训练、下载、推理等场景。

核心思路：把“终端窗口”和“正在运行的会话”分开。断开 SSH 或关闭本地窗口后，只要 tmux 会话还在，里面的程序就不会一起退出。

---

## 安装

```
# Ubuntu / Debian
sudo apt-get install tmux

# CentOS / Fedora
sudo yum install tmux

# Mac
brew install tmux
```

检查是否安装成功：

```
tmux -V
```

---

## 最常用流程

```
tmux new -s 任务名              ← 新建并进入会话
# 在里面运行程序
Ctrl+b  然后按 d                ← 分离会话，程序继续在后台跑

tmux ls                         ← 查看现有会话
tmux attach -t 任务名            ← 重新进入会话
```

例如：

```
tmux new -s train
python train.py
# 按 Ctrl+b，再按 d

tmux attach -t train
```

---

## 退出与分离

### 分离会话

```
tmux detach
```

或快捷键：

```
Ctrl+b  d
```

分离后会退出 tmux 窗口，但会话和程序还在后台继续运行。

### 真正退出

在 tmux 窗口中输入：

```
exit
```

或按：

```
Ctrl+d
```

注意：这是关闭当前 shell。若当前会话里只有这一个窗口，tmux 会话也会结束。

---

## 前缀键

tmux 的快捷键一般都要先按前缀键：

```
Ctrl+b
```

例如查看帮助：

```
Ctrl+b  ?
```

意思是：先按 `Ctrl+b`，松开后再按 `?`。

退出帮助界面：按 `q` 或 `Esc`。

---

## 会话管理

### 新建会话

```
tmux new -s 会话名
```

### 查看会话

```
tmux ls
```

或：

```
tmux list-session
```

### 接入会话

```
tmux attach -t 会话名
```

也可以用编号：

```
tmux attach -t 0
```

### 切换会话

```
tmux switch -t 会话名
```

### 重命名会话

```
tmux rename-session -t 旧名字 新名字
```

如果当前就在这个会话里，也可以用快捷键：

```
Ctrl+b  $
```

### 杀死会话

```
tmux kill-session -t 会话名
```

---

## 窗口管理

一个 tmux 会话里可以有多个窗口。可以理解为同一个终端里的多个标签页。

### 新建窗口

```
tmux new-window
```

指定窗口名：

```
tmux new-window -n 窗口名
```

快捷键：

```
Ctrl+b  c
```

### 切换窗口

```
Ctrl+b  n       ← 下一个窗口
Ctrl+b  p       ← 上一个窗口
Ctrl+b  数字    ← 切换到指定编号窗口
Ctrl+b  w       ← 从列表中选择窗口
```

### 重命名窗口

```
tmux rename-window 新名字
```

快捷键：

```
Ctrl+b  ,
```

---

## 窗格管理

一个窗口可以拆成多个窗格。适合一边跑程序、一边看日志或监控显存。

### 左右拆分

```
tmux split-window -h
```

快捷键：

```
Ctrl+b  %
```

### 上下拆分

```
tmux split-window
```

快捷键：

```
Ctrl+b  "
```

### 切换窗格

```
Ctrl+b  方向键
```

或命令：

```
tmux select-pane -U   ← 上
tmux select-pane -D   ← 下
tmux select-pane -L   ← 左
tmux select-pane -R   ← 右
```

其他常用快捷键：

```
Ctrl+b  o       ← 下一个窗格
Ctrl+b  ;       ← 上一个窗格
Ctrl+b  x       ← 关闭当前窗格
Ctrl+b  z       ← 当前窗格全屏，再按一次恢复
Ctrl+b  q       ← 显示窗格编号
```

调整窗格大小：

```
Ctrl+b  Ctrl+方向键
```

---

## 常用检查命令

```
tmux list-keys                 ← 列出快捷键
tmux list-commands             ← 列出所有 tmux 命令
tmux info                      ← 查看 tmux 信息
tmux source-file ~/.tmux.conf  ← 重新加载配置
```

---

## 建议用法

- 跑长任务前先开 tmux：`tmux new -s 任务名`。
- 会话名用具体任务名，例如 `train`、`infer`、`download`、`server`。
- SSH 服务器上跑训练、推理、下载时，不要直接在普通终端里跑，优先放进 tmux。
- 断线后重新登录服务器，先 `tmux ls`，再 `tmux attach -t 会话名`。
- 不确定快捷键时，在 tmux 里按 `Ctrl+b ?` 查看帮助。

