# RETURN_REQUEST — searchqa 旧 run 产物回传（审计用）

> **背景：** searchqa 的 QD 实验是在**流程定义之前的旧分支**上跑的（公司侧自行扩展，
> 无 provenance）。其「QD 对 SkillOpt 微弱增益」目前**不可归因**——不知道 descriptor
> 当时读到了什么（searchqa 轨迹无 code.py，代码特征 descriptor 可能塌缩 → n_occupied=1
> → QD 机制性退化为贪心，增益只是噪声）、不知道两臂预算是否相等、不知道 Archive 是否
> 带着 S1 修掉的 bug。本请求让公司把那次 run 的产物打包回传，我方据此判定：
> **可抢救 / 需按新流程重跑 / 诚实判废**。
>
> **用法：** 把下面 ```text 块整段复制，发给公司侧 agent。零训练、零 API 调用、零费用，
> 纯找文件 + 打包。

```text
在公司，

【角色铁律】你是公司侧执行 agent，公司模式（runs-only）：本任务只是定位旧产物并打包回传，
全程不跑任何实验、不调任何 API、零费用；绝不改代码、绝不 commit、绝不 push、绝不删除任何
文件。每步做完先报告再下一步；找不到的东西就停下来问 operator，不要猜、不要脑补。

【背景】之前（项目流程定义之前）在一个旧分支上跑过 searchqa 的 QD 实验（K=1 贪心 vs K>1 QD，
对比出微弱增益）。我方需要那次 run 的完整产物做机制审计。注意：那次实验可能不是用
scripts/run_experiment.py 跑的，目录结构可能和现在的文档不一致——按"内容"找，不要按文件名死磕。

— 步骤 1：定位（先做这步，报告后再继续）—
找到当时 searchqa 实验的两个目录：
  (a) 代码目录（当时跑实验用的那份代码 checkout）
  (b) 输出目录（rollout 产物 / 日志 / 结果所在）
找不到就问 operator 当时在哪台机器哪个路径跑的。
报告：两个目录的绝对路径 + 大小（Linux: du -sh；Windows PowerShell:
"{0:N1} MB" -f ((Get-ChildItem -Recurse | Measure-Object Length -Sum).Sum/1MB)）。

— 步骤 2：代码 provenance（必须，KB 级）—
在代码目录里执行（全部只读）：
  git rev-parse HEAD
  git branch --show-current
  git status --short
  git log --oneline -10
  git diff master...HEAD > searchqa_branch_vs_master.patch   （没有 master 就试 main；都没有就跳过并说明）
  git diff > searchqa_uncommitted.patch                       （捕获未提交改动）
把前四条的输出原样存进 provenance.txt。
若代码目录不是 git 仓库：把整个代码目录打包（排除 .venv/、数据目录、输出目录），这是兜底的
"实际跑过的代码"快照。

— 步骤 3：运行参数（必须；不知道的写 UNKNOWN，绝不编造）—
收集当时的运行配置，写进 run_params.txt：
  - 启动命令（查 shell history：history | grep -iE "searchqa|python" 或问 operator）
  - target 模型名 / optimizer 模型名 / endpoint 类型（⚠️ 只要类型和模型名，绝不要 API key）
  - 题数 N、评估预算或轮数、K 值、candidates per step
  - target/optimizer 的 temperature 和 seed 设置
  - 大致起止时间
  - 当时口头汇报的"增益"具体数字：对比双方各是什么、各多少分、在哪个 split 上

— 步骤 4：结果产物（按优先级收集；全都要，单项太大再按级裁剪）—
P1 机制诊断（必须，KB-MB 级）：
  - summary.json 或任何最终报告/汇总文件（若有）
  - 完整 stdout/运行日志；太大就取最后 1000 行 + 用 grep 抽全量：
    grep -inE "n_occupied|occupied|cell|descriptor|archive|accept|reject|gate|cross_cell" <日志> > mechanism_lines.txt
P2 每题分数明细（必须，MB 级）：
  - per-item 结果文件（每题 EM/score 的 json/jsonl/csv），至少覆盖三个 skill：
    baseline（初始）、贪心臂最终、QD 臂最终。有所有中间候选的更好。
P3 轨迹样本（抽样即可）：
  - predictions/（或同义的逐题输出目录）下，baseline 和 QD-best 两个 skill 各取 5 题的
    完整子目录（conversation/answer 等原文件）。
P4 skill 文本（KB 级）：
  - initial skill 全文 + 各臂最终/最优 skill 全文（+ 如有：每次被接受的候选 skill）。

— 步骤 5：打包回传 —
若输出目录整体 < 2GB：直接整目录打包，外加步骤 2/3/4 的散件：
  Linux: zip -r returned-searchqa-audit.zip <输出目录> provenance.txt run_params.txt *.patch
         sha256sum returned-searchqa-audit.zip
  Windows: Compress-Archive -Path <同上> -DestinationPath returned-searchqa-audit.zip
           Get-FileHash returned-searchqa-audit.zip -Algorithm SHA256
否则按 P1→P4 优先级装包，P3 只抽样。
把 zip + sha256 发回我方（不 commit、不 push）。

【出错处理】任何一步找不到/报错：停，把"第几步 + 你看到的目录列表（ls 输出）+ 报错原文"
发回我方。不要自行修复、不要重跑实验、不要删任何东西。
```

## 我方收到后判定什么（审计清单）

| 检查 | 来源 | 判定 |
|---|---|---|
| 当时跑的代码 = 哪个 SHA、与 master 差什么 | provenance.txt + patch | 是否带 S1 前 Archive bug / descriptor 读了什么 |
| n_occupied / cell 分布 | P1 mechanism_lines | **>1 = QD 机制真实参与；=1 = 增益不可归因于 QD** |
| 两臂评估次数是否相等 | P1 日志 + run_params | 等预算红线是否成立 |
| 增益的统计显著性 | P2 每题明细 → paired bootstrap/McNemar | "微弱增益"是信号还是噪声 |
| searchqa 轨迹长什么样 | P3 样本 | 离线设计文本行为 descriptor（QD 扩展到非代码 benchmark 的原料） |

**三种结局**：① 机制成立 + 等预算成立 → 结果可抢救入论文（补统计检验）；② 任一不成立 →
searchqa 需按新流程重跑（先做文本 descriptor + probe 门）；③ 产物缺失到无法判定 → 判废，
论文不提。任何一种都比现在的"不可归因"强。
