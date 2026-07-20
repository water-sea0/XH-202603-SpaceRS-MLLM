---
title: AutoDL 远程 VS Code 中 Codex 的 SSH 反向代理复现指南
date: 2026-07-15
status: 已复现
tags:
  - Codex
  - VS Code
  - Remote SSH
  - SSH 反向端口转发
  - AutoDL
  - Clash
---

# AutoDL 远程 VS Code 中的 SSH 反向代理复现指南

> 本文记录一套已经成功复现的操作流程。  
> 当前先以“能够稳定复现”为准，具体触发原理以后再分析。

## 适用场景

- 本地电脑：Windows。
- 本地代理：Clash/Mihomo，HTTP 或 Mixed 端口可用。
- 远程服务器：AutoDL、SeetaCloud 或类似 Linux 容器。
- 开发方式：VS Code Remote SSH。
- 目标：让远程 VS Code 中的梯子正常连接并使用。

## 参数约定

请按自己的环境替换以下变量：

```text
<LOCAL_CLASH_PORT>   本地 Clash 端口，例如 7890
<REMOTE_PROXY_PORT>  远程反向转发端口，例如 17890
<SSH_HOST>           远程服务器 SSH 地址
<SSH_PORT>           远程服务器 SSH 端口
<SSH_USER>           SSH 用户名，AutoDL 通常为 root
```

下文示例使用：

```text
LOCAL_CLASH_PORT=7890
REMOTE_PROXY_PORT=17890
```

## 第 1 步：修改远程服务器的 ~/.bashrc

先通过 VS Code Remote SSH 或普通 SSH 登录服务器。

打开文件：

```bash
nano ~/.bashrc
```

把下面内容放到文件最开头：

```bash
export http_proxy=http://127.0.0.1:17890
export https_proxy=http://127.0.0.1:17890
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
export ALL_PROXY=$http_proxy
export all_proxy=$http_proxy
export NO_PROXY=localhost,127.0.0.1,172.16.0.0/12
export no_proxy=$NO_PROXY
```

如果远程转发端口不是 `17890`，请统一替换。

保存后，关闭当前 VS Code 的远程连接。

## 第 2 步：在 Windows 建立 SSH 反向转发

确认本地 Clash 正在运行，并且本地 `127.0.0.1:7890` 可以作为 HTTP 或 Mixed 代理使用。

在 Windows PowerShell 或 Windows Terminal 中执行：

```powershell
ssh -N -T -C `
  -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=30 `
  -R 17890:127.0.0.1:7890 `
  -p <SSH_PORT> `
  <SSH_USER>@<SSH_HOST>
```

也可以写成一行：

```powershell
ssh -N -T -C -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 17890:127.0.0.1:7890 -p <SSH_PORT> <SSH_USER>@<SSH_HOST>
```

运行后窗口没有输出、一直停在那里，通常是正常现象。

不要关闭这个 PowerShell 窗口，否则反向隧道会立即中断。

此时链路为：

```text
远程服务器 127.0.0.1:17890
        ↓ SSH 反向隧道
Windows 本机 127.0.0.1:7890
        ↓
本机 Clash 当前选中的节点
```

## 第 3 步：重新连接 VS Code Remote SSH

保持 PowerShell 中的反向隧道运行。

重新打开 VS Code，并重新连接远程服务器。

这样重新启动的 VS Code Server、extensionHost 和插件进程更有机会继承 `~/.bashrc` 中的代理环境变量。

## 第 4 步：检查远程代理连接

在 VS Code 的远程终端中执行：

```bash
curl -I -x http://127.0.0.1:17890 \
  --connect-timeout 10 \
  --max-time 30 \
  https://github.com
```

也可以使用详细模式：

```bash
curl -v -x http://127.0.0.1:17890 \
  --connect-timeout 10 \
  --max-time 30 \
  https://github.com
```

以下结果通常都说明网络链路已经建立：

```text
HTTP 200
HTTP 301
HTTP 302
HTTP 403
```

使用 `curl -v` 而不加 `-I` 时，终端可能打印大量 HTML，这是正常的网页正文，不是报错。

到这一步应该就可以随意下载外网资源了，如果需要进一步使用codex等ai工具，可以继续往下看

## 第 5 步：尝试安装官方 Codex CLI

在远程终端执行：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

本次实测流程中，这一步可能耗时较长。如果时间实在过长，也可以在出现 installing 后先手动 ctrl + c 停止。

即使后续终端里执行：

```bash
codex --version
```

仍提示：

```text
codex: command not found
```

也先继续完成后面的插件操作，不要在这里反复重装系统或修改 PATH。

## 第 6 步：清理 VS Code 中的 AI 插件

在远程 VS Code 窗口中：

1. 保留 GitHub Copilot。
2. 卸载其他 AI 编程插件。
3. 卸载 Codex 插件。
4. 等待卸载操作完成。

这一流程的目的是尽量排除多个 AI 插件、旧进程和扩展宿主状态之间的干扰。

## 第 7 步：在当前远程终端再次设置代理变量

在 VS Code 当前远程终端中再次执行：

```bash
export http_proxy=http://127.0.0.1:17890
export https_proxy=http://127.0.0.1:17890
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
export ALL_PROXY=$http_proxy
export all_proxy=$http_proxy
export NO_PROXY=localhost,127.0.0.1,172.16.0.0/12
export no_proxy=$NO_PROXY
```

检查变量：

```bash
env | grep -i proxy
```

再次检查代理：

```bash
curl -I -x http://127.0.0.1:17890 \
  --max-time 30 \
  https://github.com
```

## 第 8 步：重新安装 Codex 插件

在 VS Code 扩展市场中重新安装官方 Codex 插件。

安装后打开 Codex 面板，使用官方 ChatGPT 账号登录并测试。

本次实测中，完成上述完整顺序后，Codex 可以正常连接并工作。

## 第 9 步：确认实际运行状态

即使远程 Shell 中没有全局 `codex` 命令，VS Code 插件仍可能使用插件自带的 Codex 可执行组件，并由 `extensionHost` 启动 `codex app-server`。

可用下面命令查看相关进程：

```bash
ps -eo pid,ppid,cmd | grep -Ei '[c]odex|[o]penai|[e]xtensionHost'
```

因此：

```text
codex: command not found
```

并不能单独证明 VS Code Codex 插件没有运行。

## 常见问题

### 1. 反向转发端口创建失败

如果 PowerShell 提示：

```text
remote port forwarding failed for listen port 17890
```

说明远程端口可能已被占用。

把 `17890` 改成其他未占用端口，例如 `17891`，并同步修改 `~/.bashrc` 和测试命令。

### 2. curl 返回 unexpected eof

如果出现：

```text
SSL routines::unexpected eof while reading
```

先检查 Windows 本机 Clash：

- 是否已经选择可用节点；
- 本地代理端口是否确实为 `7890`；
- 本机浏览器是否能正常通过 Clash 访问目标网站。

### 3. Codex 一直转圈

按顺序检查：

1. Windows 的 SSH 反向隧道窗口是否仍在运行；
2. `curl -I -x http://127.0.0.1:17890 https://github.com` 是否成功；
3. 代理变量是否位于远程 `~/.bashrc` 开头；
4. 修改 `~/.bashrc` 后是否断开并重新建立过 VS Code Remote SSH；
5. 是否已经卸载并重新安装 Codex 插件。

### 4. PowerShell 窗口像卡死一样

使用 `ssh -N -T` 时没有交互提示是正常的。

这个窗口的任务只是维持隧道，不要在里面继续输入其他命令。

### 5. 本地 Clash 端口不是 7890

把所有命令里的本地端口 `7890` 替换为 Clash 实际的 HTTP 或 Mixed 端口。

## 安全提醒

默认写法：

```powershell
-R 17890:127.0.0.1:7890
```

应让远程代理入口仅供远程服务器本机访问。

不要主动改成：

```text
0.0.0.0:17890
```

否则可能把自己的本地代理间接暴露给公网或同一网络中的其他用户。

订阅链接、代理节点凭据、SSH 私钥和登录令牌不要写入知识库。

## 已验证的完整顺序

```text
1. 在远程 ~/.bashrc 开头写入代理变量
2. 关闭 VS Code Remote SSH
3. Windows 建立 SSH 反向端口转发
4. 重新连接 VS Code Remote SSH
5. 使用 curl 验证 127.0.0.1:17890
6. 尝试安装官方 Codex CLI
7. 卸载除 Copilot 外的其他 AI 插件，包括 Codex
8. 在当前远程终端再次 export 代理变量
9. 重新安装 Codex 插件
10. 登录并测试 Codex
```

## 当前结论

这套流程已经在新的短租服务器上成功复现。

目前尚未确认真正的触发因素究竟是：

- `~/.bashrc` 中的代理环境变量；
- VS Code Remote SSH 重连；
- SSH 反向端口转发；
- Codex CLI 安装过程产生的副作用；
- Codex 插件卸载与重新安装；
- extensionHost 或 `codex app-server` 的重新启动；
- 或以上因素的组合。

现阶段先尊重复现结果，保留完整顺序，不随意删减步骤。原理分析另行进行。
