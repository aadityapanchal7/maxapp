## FITMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Use **HH:MM** 24h; follow COMPUTED ANCHOR TIMES + full reference (pre-workout **workout−30m**, post **session_end+15m**).
2. **Do NOT** use a generic wake-only check-in as the first FitMax ping — first daily anchor is **morning nutrition at wake+30** (merge with SkinMax AM when both active).
3. **Quiet hours:** no tasks between sleep_time and wake_time.
4. **Workout days only:** pre + post training tasks; **rest days:** omit pre/post.
5. **Monday:** weekly weigh-in at **wake+15** (checkpoint).
6. **1st of month:** monthly body check at **midday** anchor (checkpoint).
7. **Phase-in:** if `fitmax_weeks_on_program` is 1–2, omit evening nutrition + posture + monthly except weigh-in; weeks 3–4 add PM nutrition + supplements if opted in; week 5+ full module set per reference.
8. **BoneMax active:** remove neck work from lift descriptions; **replace** midday posture tips with training/nutrition tips (no posture duplication).
9. **HeightMax active:** after leg days with squats/deadlifts, optional **dead hang 2 min** copy in post-workout or evening task.
10. **SkinMax active:** merge morning nutrition + AM skincare into **one** notification when possible.
11. **HairMax active:** when scheduling creatine tip, add **DHT/hair caveat** for predisposed users.
12. **task_type:** `routine` for nutrition blocks; `reminder` for cues; `checkpoint` for weigh-in, monthly photos, progressive-overload reviews.
13. Cap **10** notifications/day **across all modules**; stagger with MULTI-ACTIVE-MODULES instructions.
