# Evo VisualNovel 交接记录

更新时间：2026-08-15（Asia/Shanghai）

## 当前目标

在 `evo-visualNovel` 分支上，用 DeepSeek `deepseek-v4-flash` 实际生成一个 5 节点、
封闭结局的中文校园谋杀案，同时保留原项目的 Actor 驱动结构。

必须保持的生成责任边界：

```text
Producer -> Core GDD + global goal
Designer -> 每个节点只生成一个 NodeGoal
Writer/Director -> 选择下一位 Actor，并给出简短表演意图
Actor -> 独立生成 thought / action / dialogue / image
Writer -> 只把 Actor 输出编译成 VN 标签，不发明或改写 Actor 台词
Producer -> 验证 NodeGoal，并只提交有文本证据支持的状态变化
```

Actor 不是审核器。Actor 必须继续亲自生成动作和台词；Writer 不得替 Actor 写台词。

## 工作区状态

- 仓库：`/Users/deceivemaster/Code/AI4Game/AI4VisualNovel`
- 分支：`evo-visualNovel`
- 工作区已有大量未提交改动，其中包含用户原有改动；不要 reset、checkout 或清理。
- checkpoint schema：`rolling-state/3.2`
- 测试：`43 passed`
- API 密钥没有写入仓库或 `.env`。后续运行也必须只通过进程环境变量注入。

关键文件：

- `workflow.py`：`run_rolling_story`、Actor 驱动节点生成、Producer fail-closed gate
- `agents/designer_agent.py`：每节点一个 NodeGoal
- `agents/producer_agent.py`：节点审核和 evidence-backed state reduction
- `agents/writer_agent.py`：Actor 输出的确定性 VN 编译和台词保真校验
- `agents/actor_agent.py`：Actor 独立表演
- `agents/schemas.py`：Core GDD、NodeGoal、Producer review schema
- `data/campus_murder_node_goals_5/rolling_state.json`：可恢复 checkpoint
- `data/campus_murder_node_goals_5/story.txt`：当前只保留 `root`；其余节点等待按新连续性协议重生
- `data/campus_murder_node_goals_5/backups/before_rollback_20260815_164159/`：旧 4 节点版本和重试上下文的完整备份
- `data/campus_murder_node_goals_5/backups/before_rollback_20260815_170648/`：切换 Flash 后中断的 node1 临时态备份

## 实际运行结果

DeepSeek 官方端点可以工作。旧版真实运行曾提交 4 个 Producer PASS 节点：

1. `root`：询问叶晓、赵深、韩旭，建立冲突时间线；韩旭的颜料痕迹和改口暴露。
2. `node1`：勘查美术储藏室，发现门锁细线拉磨痕迹、门缝擦痕、被清洗和移动的雕塑。
3. `node2`：搜查体育馆活动室，发现鱼线、带泥运动鞋和湿纱布；赵深解释反复，被列为首要嫌疑人。
4. `node3`：找到带血手套和伪造遗书底稿；韩旭给出八点零八分目击证言；林晨完整演示
   鱼线从门外反锁并回收的手法，确认带血迹和头发碎屑的石质雕塑就是凶器，并明确呈现
   “竞争、怨恨、要挟”的动机链。

但这些 PASS 只覆盖节点内部目标，没有审核跨节点 discourse relation。人工复核发现
`root → node1` 没有回应韩旭的问题，`node1 → node2` 缺少转去体育馆的因果桥，尤其
`node2 → node3` 在林晨已经出门找证人后又无触发地“折回储物柜”，构成行动回滚。
因此旧 4 节点版本已完整备份，正式 checkpoint 回滚到唯一不涉及跨节点连接的 `root`。
当前 `story.txt` 只有 1 个正式节点，不能声称故事已经完成。

旧版最终节点 `node4` 曾多次实际生成，但没有通过 Producer，因此没有写入正式 checkpoint，
也没有污染 Actor 的已提交记忆。最新失败稿已经做到：赵深认罪并交代动机和作案过程，
叶晓明确不再受要挟并愿意作证，韩旭完成从恐惧隐瞒到公开作证的转变，警方实际到场接收
赵深和证据，最后以独立尾声落句结束。Producer 的 closure_check 已判定冲突解决、直接后果、
人物弧、新平衡和终止信号全部为 true。

该稿仍被合理驳回，只剩两项：

1. 正文必须逐字明确“韩旭的目击证言被采纳”，不能只让韩旭重复证言。
2. 赵深供述中临时新增了“钥匙”，必须交代钥匙去向，避免新未解矛盾。

在下一轮修订开始时，DeepSeek 返回 HTTP 402 `Insufficient Balance`，实验因账户余额不足中断。
旧 `rolling_retry.json` 已随旧 4 节点故事进入备份，不再复用于新叙事。充值后应从 `node1`
重新生成，避免把旧结局反馈错误施加到新版本。

## 跨节点连续性：参考 From Persona to Person

2026-08-15 参考了 Hsu、Lin、Kao 的 2025 论文 *From Persona to Person: Enhancing the
Naturalness with Multiple Discourse Relations Graph Learning in Personalized Dialogue Generation*
（arXiv:2506.11557）。论文不把连贯性等同于流畅度，而是将 utterance 建成带 discourse
relation、顺序和 turn 信息的图，并预测下一回应类型；该思路已改造成无需训练 GAT 的
生成时硬约束：

1. 每个 NodeGoal 必须包含 `transition_contract`：关系类型、上一场景、上一说话者、上一
   节点最后 content 的逐字 `source_anchor`，以及首回合承接要求。
2. 非首节点关系限定为 acknowledgement、answer、continuation、elaboration、explanation、
   result、correction、contrast 或有因果依据的 topic_shift；首节点使用 root。
3. source scene/speaker/anchor 由工作流从已提交剧本确定性提取并覆盖模型副本，防止模型
   伪造或改写锚点。
4. Director 给第一个 Actor 的 guidance 会强制携带 relation、anchor 和 bridge requirement；
   Actor 必须先完成承接，不能直接跳到本节点任务。
5. Producer review 新增 `continuity_check`，逐项审核锚点回应、关系实现、行动连续、地点移动
   是否有触发，并引用当前节点开头的逐字证据。缺一项即 REVISE。
6. `story_graph.edges` 在目标节点规划后写入 `discourse_relation` 和 `source_anchor`，使线性
   剧情图同时成为话语关系图。
7. checkpoint 恢复和独立审计器都会 fail-closed 检查上述契约与证据。仅仅地点相同不算
   连续；上一节点已经宣布出门、下一节点无理由折返会被拒绝。

## 已针对失败做的修复

针对历次失败已经完成并验证以下修复：

1. `WriterAgent._format_actor_performances` 不再永远选择 Core GDD 的第一个场景。
2. Writer 根据 Actor action/dialogue 中明确出现的地点选择初始 `<scene>`。
3. 节点内 Actor 明确移动到另一个 Core GDD 场景时，Writer 插入新的 `<scene>` 标签。
4. 该处理只编译标签，不修改 Actor 的 action/dialogue，台词保真规则保持不变。
5. Producer 驳回反馈会加入 Director 使用的 `mandatory_revision_evidence`，并明确要求每条
   反馈都由 Actor 的可见动作或明确台词证明，全部满足前不得 STOP。
6. 新增跨地点 Actor 表演测试。
7. Producer 明确点名需要补演的角色时，流程会确定性提取这些 Actor；每位 Actor 都必须在
   修订稿中产生至少一个可见回合，全部补演前 Director 不能 STOP 或提前安排尾声。
8. 尾声必须逐字等于最后一个 `<content>` 正文，并严格位于认罪、完整动机、后果和人物弧
   之后；尾声之后不得出现新的供述、辩解或剧情。
9. 独立审计器已同步 Writer 的跨节点场景继承规则，并加入 discourse edge 审计。

随后又发现并修复了一个更严重的编译问题：结构化 Actor turn 中虽然保存了
`character`，Writer 过去却只把裸 `action` 写入旁白，导致“先看向叶晓……”等动作没有
主语。现在每条动作旁白都必须保留执行者，例如“林晨先看向叶晓……”，保真校验会逐条
核对执行者、数量、顺序和原始 action。现有 3 个 checkpoint 节点已经从 Actor 原始记录
机械重编译：`root` 为教学楼三楼走廊，`node1` 为美术储藏室，`node2` 为体育馆篮球部活动室；
三者的 Actor 台词和动作保真校验均通过。恢复 checkpoint 时也会自动执行同样的重编译，
并保留原有 jump 标签。

为解决“揭示真相后立即停住、故事没有真正结束”的问题，还加入了封闭结局门槛：

1. Designer 会给 closed 模式的最终 NodeGoal 强制追加直接后果、人物弧/关系收束、
   新平衡和明确终止信号，并把阶段固定为 `resolution`。
2. Producer review 新增 `terminal_condition_checks` 和 `closure_check`。每条全局终局条件
   都必须逐项对应，并提供最终剧本中的逐字证据；最终节点即使模型声称 PASS，只要终局
   条件、冲突解决、直接后果、人物弧收束、新平衡、终止信号或证据任一缺失，代码也会
   强制改为 REVISE。伪造或无法在剧本中找到的证据引用同样会被拒绝。
3. 实验需求文件同步写入上述尾声要求。
4. 恢复前会检查 `scripts/goals/reviews/performances/summaries` 是否按连续节点完全对齐，
   且所有已提交节点均已 PASS，避免从损坏或半提交状态继续调用模型。
5. 新增 checkpoint 重编译、closed-ending gate、必需 Actor 补演、跨节点 discourse edge
   和独立完成审计器的回归测试；完整测试为 `43 passed`。

2026-08-15 已把实验模型从 `deepseek-v4-pro` 切换为 `deepseek-v4-flash`。Flash 的 API
请求已实测返回 HTTP 200。第一次 Flash 运行暴露出默认思考模式可能只返回
`reasoning_content`、最终 `content` 为空的问题；客户端现对 DeepSeek V4 显式传入
`thinking.type=disabled`，并拒绝把空正文当作成功。相关行为有两项回归测试覆盖。

注意：地点识别目前是保守的确定性别名/文本证据匹配，不是完整的语义场景追踪器。

## 如何继续

先验证测试：

```bash
cd /Users/deceivemaster/Code/AI4Game/AI4VisualNovel
python -m pytest -q
```

然后运行实验入口。脚本会在没有环境变量时通过隐藏输入读取 DeepSeek 密钥，不把密钥放入
命令历史、文档、日志、`.env` 或代码；它从 checkpoint 恢复，允许每节点最多 5 轮审核，
结束后自动运行测试和独立完成审计：

```bash
./experiment/run_campus_murder_deepseek.sh
```

等价的手动运行方式是先在当前 shell 进程中注入 `DEEPSEEK_API_KEY`，再运行：

```bash
TEXT_PROVIDER=openai \
OPENAI_BASE_URL=https://api.deepseek.com \
OPENAI_API_KEY="$DEEPSEEK_API_KEY" \
MODEL=deepseek-v4-flash \
DEEPSEEK_THINKING=disabled \
python main.py \
  --mode evolve \
  --project campus_murder_node_goals_5 \
  --max-nodes 5 \
  --max-revisions 4 \
  --character-count 4 \
  --ending-mode closed \
  --requirements-file examples/campus_murder_5_nodes.txt
```

默认启用 resume。程序应显示“已提交 1 个节点”，从 `node1` 开始生成剩余四个节点。
不要使用 `--no-resume`，否则连已通过的 root 也会丢弃并重新调用模型。

项目文件和 `.env` 中没有保存用户提供的 DeepSeek 密钥。再次运行时仍应通过脚本的隐藏
输入注入密钥。Pro 和 Flash 都已实测返回 HTTP 200，但用户要求控制成本，本轮在 node1
提交前主动停止；完整四节点生成应在用户确认预算后再续跑。

本轮 DeepSeek 曾有一次请求约 25 分钟后才触发 SDK retry，随后恢复。长时间无输出时先检查
进程和 HTTPS 连接，不要立刻杀进程；checkpoint 已提交节点不会丢失。

## 完成前验收

只有同时满足以下条件才可向用户报告完成：

- `rolling_state.json` 中 `scripts/goals/reviews/performances` 都恰好有 5 项。
- 节点依次为 `root`、`node1`、`node2`、`node3`、`node4`。
- 每个 Producer review 都是 `PASS` 且 `goal_completed=true`。
- 最终节点明确解决凶手、手法、动机、凶器和证据链，而不是只表达怀疑。
- 最终 review 的 `closure_check` 中，冲突解决、直接后果、人物弧/关系收束、
  新平衡和终止信号全部为 true，且包含剧本文本证据。
- `node1` 至 `node4` 都有与上一节点精确锚定的 `transition_contract`；对应 review 的
  `continuity_check` 全部为 true 且包含当前剧本开头的逐字证据。
- `story_graph.edges` 除 from/to 外还包含与目标 NodeGoal 一致的 `discourse_relation` 和
  `source_anchor`。
- 每条最终角色台词与对应 Actor dialogue 的角色、数量、顺序、文字完全一致。
- `<scene>` 与 Actor 实际动作地点匹配；跨地点时存在正确的场景切换标签。
- `story.txt` 中不存在把动作或旁白塞进角色台词标签的问题。
- 最后再次运行 `python -m pytest -q`。

再运行独立的 fail-closed 审计器；只有退出码为 0 且输出 PASS 才能报告实验完成：

```bash
python experiment/audit_rolling_story.py \
  data/campus_murder_node_goals_5/rolling_state.json
```

可用下面的只读检查快速确认数量和审核状态：

```bash
jq '{
  scripts: (.scripts | keys),
  goals: (.goals | length),
  reviews: [.reviews | to_entries[] | {
    node: .key,
    decision: .value.decision,
    completed: .value.goal_completed
  }],
  performances: (.performances | length)
}' data/campus_murder_node_goals_5/rolling_state.json
```

## 仍需关注的质量问题

- Actor 的 `image` 偶尔返回单字母（如 `n/e/u/t`），可运行但表达标签质量一般。
- MemorySearch 日志会打印整段历史节点，日志噪声很大，也增加上下文体积。
- 当前输出偏舞台记录：Actor action 原样成为旁白，保证来源可信，但文学润色较弱。
- Producer 对明确措辞要求很严格。这能阻止假完成，但也可能让同一个节点多次重演，成本较高。
- Actor 回合上限会根据 completion conditions 和 Producer 反馈自适应提高，最高 32 回合；
  每节点最多 5 版（初稿加 4 次修订）。不要为了跑通而绕过 Producer gate。

## 安全说明

用户曾在对话中提供 DeepSeek 密钥。不要在回复、交接、日志或代码中重复该密钥，
不要提交任何包含密钥的文件。若怀疑密钥已进入 shell history 或外部日志，应建议用户轮换。
