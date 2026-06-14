# COLD START — QD-over-SkillOpt（2026-06-13 会话末快照）

> 新 agent（无对话记忆）：**先读这一份**，再读 `docs/QD-GAIN-investigation.md`。
> 任何动作前，用 `git status` + 检查下面 §1 的在跑任务核对真实状态——本文是某时刻快照。

---

## 0. 30 秒现状

- **项目**：QD-over-Skills = 在微软 SkillOpt（迭代优化一个自然语言"技能文档"去 condition DeepSeek 解 SpreadsheetBench 代码题）之上套 MAP-Elites。**核心赌注**：等昂贵评估预算下，维护行为多样的技能 archive（QD）能否产出比单点贪心（greedy）更好的**单个技能**。
- **本会话做了 4 件事**：(a) 把 greedy/QD 循环补成**忠于原文**（缺口 2/3）；(b) 一轮深度调查**重构了判断**；(c) 建好并接线**自适应 binning**（解锁公平测试的关键修复）；(d) **跑完第一次公平付费对照**（s1fast，QD held-out 反输，见 §9）。
- **127 个 zero-API 测试通过**。**核心代码已 commit `14e04f2`**（忠实化 + binning + **merge 红线修复**），docs/tools 探针随后提交。
- **最新状态/战略见文末 §9（2026-06-14 更新）——本节以下 §1–§6 是 2026-06-13 快照，已被 §9 覆盖处以 §9 为准。**

---

## 1. ✅ 已完成：第一次公平付费对照 `full-adaptive-s1fast`（无任务在跑；结果/战略见 §9）

后台正在（或刚刚）执行（**精简版,为最快出第一信号**）：
```
python scripts/run_experiment.py --full --gen-split train --gate-split val --num-epochs 4 --seed 1 --n 24 --tag adaptive-s1fast
```
这是**第一次公平的 K=1(greedy) vs K=4(QD+自适应binning) 对照**：忠实三集 + slow + meta + buffer + 自适应 binning **全保留**，只用 `--n 24` 把 gen=train[:24] / gate=val[:24] 缩小提速（~1h）。等预算=24，**两臂并发**（ThreadPoolExecutor）。
> 全量 N=80/40 的版本（tag `adaptive-s1`）跑了 ~1h 太慢被杀——**瓶颈是 DeepSeek 总吞吐,两臂并发只是切分同一份吞吐,墙钟没真减半**；全量是后续"可发表数字"的跑,本轮先拿方向信号。

**查结果**：`runs/full-adaptive-s1fast/summary.json`（跑完才写；含 baseline + per-arm best + verdict Q1/Q2 + n_occupied）。
- 还没有该文件 → 仍在跑。查进程：`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -like '*run_experiment*' }`。
- 实时日志在 temp（**app 重启后消失**，别依赖；摘要落 `runs/full-adaptive-s1fast/`）。
- 历史：被杀的全量跑残留在 `runs/full-adaptive-s1/`（gen/gate 集不同，**别和 -s1fast 混用**）。

**跑完要看两件事**：
- **[Q1] archive 现在散不散**：K=4 的 `n_occupied`。**关键判据**——应从历史的 ~2（旧塌缩）跳到 ~8-13（自适应 binning 在**真实行为**上生效）。若仍 ~2 → binning 没起效（warmup 太薄 / 真实行为带太窄）→ 见 §5。
- **[Q2] 真问题**：K=4 best > K=1 best（在 gate/test 上）？**1 seed 只是方向信号，不显著。**

**若任务死了/被杀/app 重启**：重跑同一条命令（`--tag adaptive-s1` 会复用 `runs/full-adaptive-s1/`，已算的 rollout 可能复用）。**先看日志有没有限流报错（429/大量异常 FAIL/单题 dt 飙升）**；若有，把 `scripts/run_experiment.py` 里那段 `ThreadPoolExecutor`（§3）**退回串行**（`r1 = run_arm(1,"k1"); rk = run_arm(plan.k, f"k{plan.k}")`）再跑。

**预登记预测（别事后挪门柱）**：忠实化越彻底，greedy 越强，QD 边际越小；中心情形 QD−greedy +0~3pts、很可能不显著。**但**这是第一次 archive 真能展开的公平测——之前的"QD 输"都不算数（见 §2）。

---

## 2. 为什么在这（本会话的重构）— 详见 `docs/QD-GAIN-investigation.md`

之前几轮把 QD 当 **ensemble/选择**（在搜索产出的最终技能里选/路由），用缓存做了 5 个零 API 探针 → 那条路 **k-fold 样本外无稳健增益**（+0.01±0.08）。**但那不是 QD 命题**：SkillOpt 是单文档迭代积累 guidance，QD 的增益必须来自**搜索动力学**（archive 作踏脚石爬到更高的单技能）。**而之前每次 QD 运行 archive 都因 binning 错位塌成 2-4 格 → K>1 退化成"近 greedy + 更差 gate" → QD 搜索从没被公平跑过。** 机制上 greedy（不可逆 strict-`>` on noisy val）有三个口子：① val 过拟合棘轮、② 过不去中性平台、③ 路径依赖；QD 的 per-cell 宽松 gate（候选只需赢自己那格）正对着它们 → 留住 greedy 丢弃的踏脚石。**结论：「QD 没用」未经证明。** binning 修复（§3）+ §1 的付费对照是第一次公平检验。

5 个探针证据链（数据在 `docs/*-probe.json`）：① 塌缩是 **binning 假象**非真塌缩（descriptor-rebin：native 4/16 vs min-max 13/16）；② in-sample 互补 headroom 巨大（+10~25）；③ 但 type-router 样本外无增益；④ fine-router 单切分 +5；⑤ k-fold 把 +5 打回 ~0（海市蜃楼）。文献依据来自 deep-research（QDAIF arxiv:2310.13032、In-context QD 2404.15794、AURORA 2106.05648、ELM 2206.08896、CVT-MAP-Elites 等）。

---

## 3. 本会话建了什么（均在 working tree，未 commit）

**缺口 3 — epoch-local rejected buffer（原文 §3.5，两臂默认开）+ 缺口 2 — optimizer meta skill（原文 §3.6，两臂都接）**
- `qd/loop.py`：`run_search` 每 epoch 维护 buffer（线程给两臂 propose + 每步 append）；持 `active_meta`，每 epoch 边界 `meta_update` 累积+线程（不改 skill 文档）；epoch 边界先抓 `epoch_best`(pre-slow) 喂 slow+meta。
- `qd/adapter_skillopt.py`：`rcv=False`=原文模式（`_buffer_context` plain render，不调 AIM/flips）/`rcv=True`=RCV；`meta_update` 复用 `_slow_rollout` + fork `build_comparison_pairs`/`run_meta_skill`；propose 传 `meta_skill_context`（零 fork 改）。
- 测试：`test_loop_buffer.py`、`test_adapter_buffer.py`、`test_loop_slow_meta.py`(含 meta)、改写的 `test_loop_ledger.py`。

**自适应 binning（修 archive 塌缩 = QD 公平测的前提）**
- `qd/descriptor.py`：新 `CellGrid`（纯 stdlib；uniform 默认 == 原 `cell_of`；`calibrate(points)` 设 frozen per-axis quantile 切点；guard：points<nbins→uniform）。
- `qd/archive.py`：新 `replace_elites()`（校准点 re-key 全部 elite）。
- `qd/loop.py`：`run_search` 加 `adaptive_bins/warmup_evals/baseline_b`；K>1 用前 `warmup_evals`(默认 min(budget//3, 一个epoch)) 个**已评估候选**的 b 校准 frozen grid（=正常步，**不额外花评估→等预算红线保住**），re-bin archive（`elite_b`+`baseline_b`），之后用 calibrated grid。K=1/off 不动。
- `scripts/run_experiment.py`：算 `base_b`，K>1 自动 `adaptive_bins=True`；**两臂 ThreadPoolExecutor 并发**（本会话末加的提速）。
- 测试：`test_cell_grid.py`、`test_loop_adaptive_bins.py`。
- **离线验证**（`tools/adaptive_binning_probe.py`）：warmup 校准 → held-out **native 2-4/16 → quantile 13-15/16**，方案成立。
- **过 code-review**（2 轮）：0 CRITICAL；缺口2/3 的 2 MEDIUM+2 LOW 已修；自适应 binning 的 2 HIGH（warmup 跨 epoch 边界 stale-b）已修（cap warmup 到一个 epoch）。

**5 个零 API 诊断探针**：`tools/{descriptor_rebin,headroom,competence_headroom,router_test,router_kfold,adaptive_binning}_probe.py` → 结果 `docs/*-probe.json`。

---

## 4. Git / working-tree 状态（未 commit）

**Modified（10，跟踪）**：`qd/loop.py` `qd/archive.py` `qd/descriptor.py` `qd/adapter_skillopt.py` `scripts/run_experiment.py` `docs/FAITHFUL-REPRO-plan.md` + 4 个改写的测试（test_adapter_rcv / test_loop_generation_path / test_loop_ledger / test_loop_slow_meta）。

**Untracked 信号文件**：4 个新测试（test_loop_buffer/test_adapter_buffer/test_cell_grid/test_loop_adaptive_bins）、6 个探针 `tools/*_probe.py`、7 个 `docs/*-probe.json` + `docs/QD-GAIN-investigation.md`、本文。

**Untracked 杂物（deep-research 副产物，可删）**：`_qdaif_*.txt` `_fig11*.png` `_ce_dump.txt` `qdaif_extracted.txt` `tools/_incontext_qd_dump.txt` `tools/_extract_qdaif.py` `tools/_elm_pdf_probe*.py`。
**Untracked LOCAL-ONLY（别入库，含密码用法）**：`tools/_autodl_ssh.py` `tools/_autodl_probe.py`。

**用户要求先不 commit。** 建议 commit 拆分（待用户发话）：
1. `feat(qd): 缺口2/3 忠实化（rejected buffer + meta skill）`
2. `feat(qd): 自适应 binning（CellGrid）修 archive 塌缩 + 两臂并发`
3. `docs: QD 增益调查 + 离线诊断探针`（probe 工具 + JSON + verdict doc）
（杂物 `_*` 先 .gitignore 或删；`tools/_autodl_*` 保持 LOCAL-ONLY。）

---

## 5. 下一步（按顺序）

1. **读 `runs/full-adaptive-s1/summary.json`** → Q1（n_occupied 散没散）/ Q2（K4 best vs K1 best）。
2. **Q1 散开 + Q2 正** → 扩 seed 2、3（`--seed 2` / `--seed 3`，各一条命令，可并行多进程）→ `tools/analyze_returned_stats.py` pooled McNemar 做配对显著性。
3. **Q1 仍塌** → 真实行为带太窄/warmup 太薄：调大 eval_budget（让 epoch0 warmup 点更多）或换 descriptor 轴；先用 `tools/adaptive_binning_probe.py` 思路在新缓存上离线复验。
4. **Q2 多 seed 仍负** → 诚实负结果 + 机制解释（领域 guidance 天花板低，见 QD-GAIN-investigation §3/§4）。两种结局都可发表。

---

## 6. 关键 caveat（务必记住）

- ⚠️ **安全**：`.env` 里的 `AZURE_OPENAI_API_KEY` 是 2026-06-08 在对话里**贴过明文**的那把 → **应轮换**。付费跑用的就是它。
- ⚠️ **未 commit**：一切在 working tree，丢了就没了。
- ⚠️ **付费**：每 seed ~¥100-150；并行 = 2× DeepSeek 并发（限流风险，§1 有兜底）。
- ⚠️ **paper-local LOCAL-ONLY**：`paper-local/skillopt-paper-fulltext.txt`（原文全文）在 `.git/info/exclude`，不 commit。

---

## 7. 文件地图

| 类 | 文件 |
|---|---|
| **入口** | 本文 → `docs/QD-GAIN-investigation.md` → `docs/FAITHFUL-REPRO-plan.md`（忠实化协议/进度）|
| QD 核心 | `qd/loop.py`(run_search 两臂+epoch+buffer+meta+自适应binning) `qd/archive.py`(MAP-Elites+replace_elites) `qd/descriptor.py`(行为轴+CellGrid) `qd/adapter_skillopt.py`(DeepSeek 适配,rcv/meta) `qd/{budget,ledger,scheduler,variation}.py` |
| 原文 fork | `SkillOpt/skillopt/engine/trainer.py`(完整实现) `…/optimizer/{slow_update,meta_skill,skill,clip}.py` `…/evaluation/gate.py` |
| 启动 | `scripts/run_experiment.py`(--full/--preflight/--dry-run/--probe-descriptor) `tools/run_qd_validation.py`(小验证) `tools/preflight_deepseek_smoke.py` |
| 探针/数据 | `tools/*_probe.py` + `docs/*-probe.json` |
| 数据集 | `SkillOpt/data/spreadsheetbench_split/{train,val,test}/items.json`(零重叠 80/40/280) `…/spreadsheetbench_verified_400/` |
| 缓存(历史跑) | `runs/full-dpsk-*`、`runs/val/*` 等（含 `<arm>/<skill_hash>/{results.jsonl, predictions/<id>/code.py}`，探针就读这些）|
| 记忆 | `C:\Users\王奕豪\.claude\projects\E--skillopt\memory\{MEMORY.md, faithful-repro-lesson.md, skillopt-repro-project.md}` |

---

## 8. 怎么跑 / 复现

```
# 零 API 单元测试（应 121 passed）
python -m pytest qd/tests -q

# 干跑：查 key/数据/fork，不花钱
python scripts/run_experiment.py --full --gen-split train --gate-split val --num-epochs 4 --seed 1 --dry-run

# 冒烟：2 题，~¥0.3，验真实管线+自适应代码不崩
python scripts/run_experiment.py --preflight --gen-split train --gate-split val --num-epochs 2 --seed 1

# 公平付费对照（§1 那条；换 --seed 2/3 加 seed）
python scripts/run_experiment.py --full --gen-split train --gate-split val --num-epochs 4 --seed 1 --tag adaptive-s1

# 离线诊断探针（零 API，读 runs/ 缓存）
python tools/descriptor_rebin_probe.py        # 塌缩=binning假象
python tools/headroom_probe.py                # in-sample 互补 headroom
python tools/router_kfold_probe.py            # 样本外路由增益（~0）
python tools/adaptive_binning_probe.py        # 自适应 binning 离线验证
```

环境：Windows + PowerShell；DeepSeek 走 `.env`（AZURE_OPENAI_* openai-compatible）；`conftest.py` 解析 `qd`/`skillopt` 路径（无需 editable 装）。

---

## 9. 2026-06-14 进展（审阅回复 + deep-research 报告 + gate-myopia 探针 + 战略岔路）

**已 commit**：`14e04f2`（忠实化 缺口2/3 + 自适应 binning + **K=1 merge 红线修复=问题A 已堵**，127 tests）；docs/tools 探针随后一并提交。**当前无任务在跑。**

**做了什么**：
- **审阅回复** `docs/REVIEWER-RESPONSE-protocol-and-evidence.md`：逐条答外部审阅 12 问。主动披露审计撞出的 3 问题：**问题A** K=1 漏 merge_patches(**已修**)；**问题B** K>1 多 epoch 下 slow/meta/buffer **全局跨格池化**(=非纯 archive，**仍未隔离**)；**问题C** descriptor 无 random/score-correlated control。
- **gate-myopia 探针** `tools/gate_myopia_probe.py` + `docs/GATE-MYOPIA-probe*.json`（零 API，within-val CV）：测"strict gate 是否短视丢可恢复价值"。**结论(负向)**：oracle 上限有(+8~18pts)但**可实现的稳健选择器(Copeland)抓不到**(cope_gain≈0，CI 全跨 0)；**QD 池无更高泛化天花板**(0.557 vs 0.555)；真瓶颈像 **D_sel 信噪比**(gate-best 几乎从不是 holdout-best，discard 65–100%)。

**外部 deep-research 报告**（用户提供，在 Downloads）：别押 QD-A；先修忠实基线 → **EES（Empirical Edit Selection：用 evaluator 经验筛 edit，打 merge/rank 瓶颈）** → **Lookahead（near-miss shadow branch，打 myopic gate）**；QD 要加先 **QD-B（archive 当 in-context proposer）** 非 QD-A；**routed skillbank 砍掉**（=已证伪 ensemble）。无信号则 pivot OfficeQA/ALFWorld。

**战略判断（三方收敛）**：k-fold 蜃楼 / s1fast test 反输 / gate-myopia **三个独立角度都指向"多样性·短视价值样本内蜃楼、样本外抓不回"** → **EES + 更大/更干净 D_sel 比 Lookahead/QD-A 更有据**。保留：EES 用 D_sel 子集筛 edit = 把 edit 选择也拟合 D_sel，小 D_sel 易过拟合(SkillOpt 的 LLM-ranking 不看 D_sel 反而正则)，只认 held-out。**唯一还没被测的 QD 机制 = 变异链踏脚石**（rejected→变异→更高），需 lineage 落盘 + 实跑才能证伪。

**下一步候选（未定，等用户拍板）**：(b) EES 可行性离线检查 / (c) MVE-0 lineage 落盘让踏脚石可证伪 / 修问题B（K>1 per-cell 隔离）/ 更大 D_sel 重跑。**付费多 seed 在补齐机制前价值有限。**

**caveat**：⚠️ `.env` DeepSeek key 仍待轮换（曾明文暴露）。⚠️ 报告引的 OfficeQA/ALFWorld 数字未经我们核实。
