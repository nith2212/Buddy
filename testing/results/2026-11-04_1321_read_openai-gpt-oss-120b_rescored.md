# Read-call eval: openai/gpt-oss-120b

- When: 2026-11-04 17:06
- Exact kind: **72/84 (86%)**
- Same next stage (what the user feels): **79/84 (94%)**
- Caught by patterns, no model call: 17

| Should be | n | Right | Read instead as |
|---|---|---|---|
| idk | 9 | 9 | - |
| answer | 10 | 7 | confirm ×2, reject ×1 |
| confirm | 14 | 14 | - |
| reject | 6 | 6 | - |
| unsure | 9 | 8 | confirm ×1 |
| own_plan | 13 | 11 | confirm ×1, reject ×1 |
| wants_move | 5 | 4 | own_plan ×1 |
| ack | 8 | 6 | own_plan ×2 |
| new_cause | 6 | 5 | answer ×1 |
| bigger | 4 | 4 | - |

## Misses

| Stage | Buddy said | User said | Should be | Read as | Same route? |
|---|---|---|---|---|---|
| open | Finish Nixly app is due in about 3 days. What feels risky about it? | people will think it's messy and unprofessional | answer | confirm (afraid) | **no** |
| purpose | What could it give you, a skill, money, someone's trust? | No I mean I already know everything about this task, which is why ik it's useless and I am not learning anything new. Ugh | answer | confirm (bored) | yes |
| micro | What about just opening VS Code and making a folder for it? | That's all? | answer | reject | yes |
| narrow | Is it more boring, or more pointless? | pointless | confirm (bored) | confirm | yes |
| narrow | Is it more boring, or more pointless? | It's more like pointless | confirm (bored) | confirm | yes |
| narrow | Is it more that you're worried others will see it and think it's not good? | yeah but also I'm not sure I can do it | unsure | confirm (afraid) | **no** |
| reframe | Want to try a deliberately rough version no one sees? What do you say? | Haha yeah that sounds fun. | own_plan | confirm (afraid) | yes |
| open | Why does Update the client invoices need doing at all? | honestly it's optional, I'll just drop it for now | own_plan | reject | **no** |
| offer | Want a tiny first move, or do you already know what you'll do? | maybe just a tiny thing | wants_move | own_plan | **no** |
| release | Love that plan. I'm here if you get stuck. | Okay! I'll try that! | ack | own_plan | yes |
| release | Love that plan. I'm here if you get stuck. | Fine bro I'll do that. Bye | ack | own_plan | yes |
| open | How was your day? | it's fine, I'm just scared of messing it up | new_cause (afraid) | answer | **no** |