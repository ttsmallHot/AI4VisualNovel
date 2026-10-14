# AI4VisualNovel Dashboard

这是 AI4VisualNovel 的本地 Web Dashboard。默认只扫描源码仓库内的
`games/<game>`，不自动合并外部目录或旧的 `data/` 项目。
例如《校园晚风》保存在 `games/wanfeng/`，包含剧本、设计、图片和 `.ai4vn/` 运行记录。

## 启动

```bash
cd AI4VisualNovel
python dashboard/server.py --port 8765
```

打开 `http://127.0.0.1:8765`。

也可以明确指定独立项目区：

```bash
python dashboard/server.py --port 8765 \
  --projects-root /path/to/games
```

## 功能

- 游戏库右上角“新建游戏”打开独立创建页（`/create.html`），可填写故事、场景、角色数量和 OC 资料。每位 OC 可上传 PNG/JPEG/WebP 立绘（每张最大 8 MB、2000 万像素，总计最大 24 MB），预览并指定主角。图片转换为 PNG 后保存在项目 `.ai4vn/oc/`，通过 `oc.characters[].neutral_image_path` 接入原有 OC 导入与表情生成流程。创建后进入项目总览；创建本身不调用模型，同名目录不会被覆盖。
- 游戏库首页只列出 `games/` 中含视觉小说文件的子目录（`game_design.json`、`story_graph.json`、`story.txt` 或 `.ai4vn/design_input.json`），可搜索和预览场景图；进入游戏后显示项目总览
- 卡片节点数读取 `story_graph.json.nodes`，角色/场景数读取 `game_design.json.characters/scenes`；这些是设计数量，不代表生成或审核已全部完成。
- 项目内的角色/场景/节点/图片数量统计，以及返回游戏库的导航
- 左侧“游戏”页面可在浏览器试玩已有剧情：背景、立绘、CG、对白推进、分支跳转及重新开始；不调用模型、不需要 Ren'Py SDK。当前不提供持久化存档，刷新页面会重置，条件指令暂不支持。
- 可平移、缩放和拖动节点的 StoryGraph 画布
- 节点摘要、前后关系、分支选项和剧本片段详情
- 故事图工具栏的“编辑故事图”（或节点详情的“编辑节点与分支”）可手动修改摘要、类型，增删节点与连线，调整选项文字。新增节点默认连接当前节点，多分支需补齐选项文字。
- 保存会检查 root、悬空连线、重复连线、循环、不可达节点和文件版本冲突，同步 `story_graph.json` 与已有 `game_design.json.story_graph`，原文件备份到 `.ai4vn/backups/story_graph/`。图编辑只改变规划，不自动重写 `story.txt`，删除图节点也不会删除剧本或素材；试玩与导出仍以剧本为准。
- `story.txt` 按节点阅读与编辑，保存时只替换当前节点正文
- 角色立绘和背景资产预览
- 每张已有的 PNG/JPEG/WebP 素材可“重新生成”，填写修改要求后沿用游戏设定、原图及角色参考图生成候选。支持关闭窗口后继续、重新打开查看进度、新旧对比、采用或保留原图。采用时校验原图是否被其他任务修改，旧图备份至 `.ai4vn/backups/assets/`，候选与任务记录保存在 `.ai4vn/regenerations/`；导出包需重新导出才能包含新图。图片模型使用项目配置，可通过 `IMAGE_OPENAI_BASE_URL` / `IMAGE_OPENAI_API_KEY` 单独指定图片服务。
- 单张重生成复用 Artist 原有入口：角色的修改要求经 `generate_character_images(feedback=...)` 进入 `_generate_single_image()` / `_build_prompt()`，与 Actor 审核意见共用重绘逻辑；背景、CG、封面调用各自的 Artist 方法。通过可选 `output_dir` 写入候选目录，不修改全局路径，不启动 Actor 自动审核循环。
- 总览可对已有项目依次启动 `design`、`script`、`render` 任务
- “生成设定”会先打开配置表单：故事要求和场景清单写入项目 `requirements.txt`，指定角色与数量保存在 `.ai4vn/design_input.json`；指定角色由现有设计流程锁定，场景作为模型生成要求
- 导出 Ren'Py 项目
- 下载 Ren'Py 项目压缩包
- 在服务器安装 Ren'Py SDK 后一键构建

项目 Agent 不在当前前端页面中；Ren'Py 导出、下载和编译操作位于项目总览。

## Ren'Py 构建

仅导出不需要 SDK。要启用编译，在运行 Dashboard 的服务器上设置：

```bash
export RENPY_SDK=/path/to/renpy.sh
python dashboard/server.py --port 8765
```

默认使用 `<renpy-sdk> <project> distribute`。如服务器需要自定义命令，可设置
`RENPY_BUILD_COMMAND`，支持 `{renpy}`、`{project}`、`{target}` 占位符。

导出的项目位于 `<project>/.ai4vn/builds/renpy_project/`，不会覆盖剧情和图片素材。
网页中的“下载导出包”会将该目录打包为 ZIP；如果尚未导出，服务会先自动生成项目文件。
