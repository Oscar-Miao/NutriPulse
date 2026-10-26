# GitHub 上传与 Flutter 迁移分支说明

适用目录：`E:\AndroidProject\AppDemo`。以下命令在 PowerShell 中执行。

## 1. 这次怎么安排版本

- `main`：先保存并上传当前原生 Android 版本。
- `android-baseline`：给当前版本打一个固定标签，便于以后找回迁移起点。
- `flutter-migration`：从当前版本创建的开发分支，用来改写 Flutter 客户端。

分支共用同一个项目目录。切换分支时，Git 会把已经提交的文件切换到对应版本，不需要复制整个项目。未提交的修改可能跟随切换，也可能阻止切换；切换前先提交，并用 `git status` 确认工作区干净。

`.gitignore` 排除的数据库、照片、本机配置不会随分支切换恢复。GitHub 保存源码版本；个人健康数据如需备份，请另外备份 `server/data`。

## 2. 第一次把当前 Android 版本上传 GitHub

在 GitHub 网站新建一个**空仓库**，不要勾选自动添加 README、`.gitignore` 或 License，因为这些文件要从本地上传。复制仓库 HTTPS 地址。官方步骤见 [GitHub 文档](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

先进入目录并初始化：

```powershell
cd E:\AndroidProject\AppDemo
git init -b main
```

如果这台电脑第一次提交 Git 代码，先设置提交身份。将示例替换成自己的名字和 GitHub 邮箱（可使用 GitHub 提供的 noreply 邮箱）。这两项是提交署名，不是登录密码：

```powershell
git config user.name "你的名字"
git config user.email "你的GitHub邮箱"
```

将源码加入暂存区并检查待提交内容：

```powershell
git add .
git status
git diff --cached --stat
```

这里不应出现 `tmp/`、`server/data/`、`local.properties`、APK、`.env` 或签名密钥。代码中直接写入的密钥不受 `.gitignore` 保护；提交前确认配置使用环境变量。

确认后保存当前版本：

```powershell
git commit -m "Save native Android baseline before Flutter migration"
git tag -a android-baseline -m "Native Android baseline before Flutter migration"
```

连接并上传 GitHub。**先将下一条命令中的地址替换成你创建的仓库地址**：

```powershell
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
git push origin android-baseline
```

GitHub 若弹出浏览器登录，完成登录即可。若提示输入密码，GitHub HTTPS 认证需要令牌或凭据管理器，不使用账户密码。

`origin` 是远程仓库的别名；`-u` 建立当前本地分支与远程分支的跟踪关系，后续一般直接执行 `git push`。

## 3. 开始 Flutter 改写前创建分支

先确认 `main` 已经提交且工作区干净，然后执行：

```powershell
git status
git switch -c flutter-migration
git push -u origin flutter-migration
git branch --show-current
```

最后一条应输出 `flutter-migration`。到这里，再让 Codex 在当前目录改写客户端，后续提交就会落在 Flutter 分支。`main` 仍保留原生 Android 版本。

`git switch -c` 的含义是“创建并切换到新分支”；只创建一次。以后回来继续改写，使用 `git switch flutter-migration`。参见 [Git 官方说明](https://git-scm.com/docs/git-switch)。

## 4. Flutter 改写过程中保存并上传

每完成一个可以运行的阶段，先查看当前分支与修改，再提交：

```powershell
git branch --show-current
git status
git diff --stat
git add .
git diff --cached --stat
git commit -m "Implement Flutter client migration"
git push
```

每次提交信息可以根据实际内容修改，例如 `Build Flutter navigation and diet screen`。提交保存在本机；执行 `git push` 后才会上传到 GitHub。

## 5. 常用查看与切换命令

| 命令 | 用途 |
| --- | --- |
| `git status` | 查看当前分支、未暂存与已暂存的改动 |
| `git branch --show-current` | 查看当前分支名 |
| `git branch -vv` | 查看本地分支及其远程跟踪关系 |
| `git branch -a` | 查看本地与已获取的远程分支 |
| `git switch main` | 切回已保存的 Android 主分支 |
| `git switch flutter-migration` | 切回 Flutter 开发分支 |
| `git log --oneline --graph --decorate --all -15` | 查看最近提交与分支关系 |
| `git diff main...flutter-migration --stat` | 查看 Flutter 分支相对共同起点的修改规模 |
| `git remote -v` | 查看远程仓库地址 |
| `git fetch origin` | 获取远程分支信息，不切换当前文件 |
| `git pull --ff-only` | 在无分叉时更新当前跟踪分支，否则停止并提示 |

切回旧版本前先提交。已忽略的构建缓存仍可能保留在磁盘上，必要时重新构建客户端。

## 6. Flutter 验收通过后是否合并

如果只想在 GitHub 同时保留两种版本，保留 `main` 与 `flutter-migration` 就可以，不必合并。

如果决定让 Flutter 成为主版本，先将 Flutter 分支推送完成，再在 GitHub 创建 Pull Request：`base: main`，`compare: flutter-migration`。检查改动后合并。合并会更新 `main`，而 `android-baseline` 标签仍指向原来的 Android 版本。

合并完成后，本机更新主分支：

```powershell
git switch main
git pull --ff-only
```

## 7. 本项目已配置的忽略范围

- Gradle、Kotlin、Android、Flutter 的缓存和构建产物。
- Android Studio、VS Code 与操作系统生成的本机状态文件。
- Python 虚拟环境、字节码、测试缓存与覆盖率输出。
- `server/data/`（含健康数据库、备份及其中的文件）、`server/media/`、`tmp/`、`output/`。
- `.env` 等本机环境配置，以及常见签名密钥；脱敏的 `.env.example` 等示例保留。

源码、数据库迁移 SQL、测试、文档、Gradle Wrapper 和 Flutter 应用的 `pubspec.lock` 应提交。

`.gitignore` 只影响未跟踪文件。如果以后发现某个本机文件已经提交，需要先确认影响，再从 Git 索引中移除；单纯新增忽略规则不会将它从历史记录中删除。
