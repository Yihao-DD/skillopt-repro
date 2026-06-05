# T001 — K=1 回归测试（档案单格 == SkillOpt）

- **目标(一句话)**：实现并自动验证——当档案只有一个 cell（$K=1$）时，QD 的选择/档案逻辑 `U` 与 SkillOpt **逐决策等价**（命题 3.6）。
- **为什么**：这是成功判据 **C0**，也是「不拆 SkillOpt 四面墙」承诺的**可机检红线**。日后任何对档案 / gate 的改动，跑这条若 fail，立刻知道改崩了。$K=1$ 时 descriptor 不参与（一切落入同一 cell），故本测试纯查**选择逻辑**。
- **依赖**：T000（DONE，有可跑的 `SkillOpt/` fork）。**前置动作：先深读 `SkillOpt/` 源码**——尤其 accept 规则、`current` 与 `best` 的追踪（见其 Algorithm 1 实现）、rejected buffer、slow/meta 与受保护字段如何与 accept 交互。**不依赖 API，可立刻做。**

## 范围内
- 实现 `U` 的 $K=1$ 配置（单 cell）。
- 一个**确定性 replay 测试**：用固定的 `(candidate, f_score)` 序列分别喂 (a) SkillOpt 的接受逻辑 与 (b) QD-at-$K{=}1$ 的 `U`，断言两者**逐步**的 accept/reject、`(current, best)` 状态、最终 `best_skill.md` 完全一致。
- 在 $K=1$ archive 里**精确复现** SkillOpt 的 `current`/`best` 双轨语义。

## 范围外
- descriptor / 多 cell / 变异多样性（$K>1$ 的东西）。
- 端到端真实 LLM run 的逐 token 复现（不可行；用 mock replay **隔离选择逻辑**）。
- 任何昂贵付费实验（被 BLOCKER-1 阻塞，且本测试不需要）。

## 要先确认的一个关键语义（读源码回答，写进 summary/ADR）
SkillOpt 区分 `current`（链条工作点，accept 与之比较）与 `best`（历史最优，导出 `best_skill.md`）。我们的 MAP-Elites 里「cell elite」是单调不降的（命题 3.4）。**$K=1$ 时 cell elite 必须扮演与 SkillOpt 一致的角色，使 accept/reject 决策逐步可复现。**
→ 必须从源码确认：**SkillOpt 的 accept 究竟与 `current` 还是 `best` 比？`current` 与 `best` 是否/何时分叉？slow-update 候选如何过 gate？** 然后让 $K=1$ 的 `U` 与之对齐。**不要凭转述实现——以真实代码为准。**

## 验收标准（可勾选、可机检）
- [ ] 在本 spec 旁或 ADR 写下**已确认的 SkillOpt accept 语义 + `current`/`best` 追踪规则**（含 slow-update 候选过 gate 的方式）。
- [ ] `U` 在 $K=1$ 下与上述语义对齐。
- [ ] **确定性 replay 测试通过**：给定固定 `(candidate, f)` 序列，QD-at-$K{=}1$ 与 SkillOpt 的逐步决策、`(current,best)`、最终 `best_skill.md` **完全相同**。必须覆盖：
  - [ ] 严格 `>`、**平局拒**（`f == 现任` → reject，两边都拒）。
  - [ ] 接受后 `current` 推进、`best` 更新规则一致。
  - [ ] 首个候选（空 cell / 初始 $s_0$）的处理一致。
  - [ ] 多步后才 beat best 的情况一致。
  - [ ] rejected 候选进 buffer 的内容一致（若 buffer 影响后续决策）。
  - [ ] 受保护 slow-update 字段：step 级 edit 不可覆盖（$K=1$ 行为与 SkillOpt 一致）。
- [ ] **真实数据回归**：从 T000 那轮 run log（40 步、4 accept + 36 reject）截一段 `(candidate, f)` 序列做 replay，两边逐步一致（与手工 case 双保险）。
- [ ] 测试**在 CI 可跑、零付费 API 调用**（纯 mock，毫秒级）。
- [ ] 写 `summary.md`，把已确认语义记入，供后续任务（T005 档案/gate）直接引用。

## 实现提示
- 把 SkillOpt 的接受/状态更新抽成**可单测的纯函数**（或直接调它现有的）；QD 的 `U.update(archive, candidate, f)` 在 $K=1$ 下应产生**同样的状态转移**。
- replay 序列：**手工构造关键 case** + 从 T000 真实 log 截一段，二者都跑。
- 把这条测试接进 CI/pytest，命名如 `test_k1_reduces_to_skillopt`，作为后续一切档案/gate 改动的护栏。

## 关联
命题 3.6（归约，已证）；BRIEF §4 红线第 2 条；成功判据 C0；后续 T005（档案 + 格内 gate）。
