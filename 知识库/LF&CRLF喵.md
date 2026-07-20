# Git 中 LF 和 CRLF 的意义与区别

## 1. 它们是什么？

LF 和 CRLF 都是“换行符”，用来表示一行文本的结束。

- LF：Line Feed，表示为 `\n`
- CRLF：Carriage Return + Line Feed，表示为 `\r\n`

## 2. 为什么会有两种？

这是不同操作系统历史习惯造成的。

- Linux / macOS 通常使用 LF
- Windows 通常使用 CRLF

所以同一份代码在不同系统上编辑时，可能会出现换行符不一致。

## 3. 它们的区别

从视觉上看，LF 和 CRLF 都只是“换行”。

但在文件内容层面，它们是不同的字节序列。

这会导致 Git 认为文件被修改了，哪怕你没有改任何代码逻辑。

## 4. Git 为什么要处理它们？

Git 希望仓库里的文本文件保持一致，避免团队协作时因为换行符产生无意义 diff。

常见策略是：

- 仓库中统一保存 LF
- Windows 工作区可按需要转换成 CRLF
- 提交时再转换回 LF

## 5. 推荐做法

在项目根目录添加 `.gitattributes`：

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf


## 特殊情况：unborn branch

`unborn branch` 指的是一个分支名已经存在于当前 HEAD 指向中，但还没有任何提交。
最常见场景是：刚执行 `git init`，还没有第一次 `commit`。
此时你可能在 `main` 或 `master` 上，但这个分支还没有真正生成提交历史。
因为分支本质上是“指向某个 commit 的指针”，没有 commit 时它就处于 unborn 状态。
第一次提交之后，HEAD 才会指向真实 commit，这个分支才算正式“出生”。

## GitHub 上常见的默认 Git 结构

GitHub 上的仓库本质上是一个远程 Git 仓库，通常不直接暴露完整 `.git` 目录。
默认分支一般是 `main`，也可以在仓库设置里改成其他分支。
本地克隆后，通常会自动生成一个远程名：`origin`。
`origin/main` 表示本地记录的 GitHub 远程 main 分支状态。
本地的 `main` 通常会追踪 `origin/main`。
普通分支在远程表现为 `refs/heads/<branch>`。
标签在远程表现为 `refs/tags/<tag>`。
提交对象、树对象、blob 对象仍然遵循 Git 的对象模型。
Pull Request 在 GitHub 上有额外的协作结构，但底层仍然基于分支和提交。
GitHub 的默认工作流通常是：clone → branch → commit → push → pull request → merge。
所以可以理解为：GitHub 负责托管远程仓库、分支、标签、PR 和协作权限。
真正的版本历史仍然由 Git 的 commit graph 决定。
