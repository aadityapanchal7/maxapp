## BONEMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Every task **time** is **HH:MM** 24h, computed from wake_time and sleep_time using the reference + COMPUTED ANCHOR TIMES.
2. **Do NOT** add a generic "morning check-in / let me know you're awake" at wake for BoneMax — **Mewing morning reset AT wake** is the first ping (unless MULTI-ACTIVE-MODULES forces stagger; if Skinmax is also active, **merge** morning mewing + skin AM into one notification when same window).
3. **Quiet hours:** no tasks between sleep_time and wake_time.
4. Respect **phase budget** (1→2→3) and **hard cap 10 notifications/day** across modules; if Skinmax active, merge evening mewing night + skin PM when appropriate.
5. **task_type:** `routine` for timed blocks (mewing sets, facial, fascia, masseter session, neck); `reminder` for symmetry / meal chewing / nutrition ping; `checkpoint` for masseter recovery check, monthly bone check.
6. Encode **workout-day-only** neck tasks using user's workout schedule from context; on non-workout days, put **chin tuck copy inside midday mewing** description (not a duplicate midday task).
7. **Fascia evening:** not every day — mark fewer evenings or omit tasks on rest pattern / Skinmax conflict nights per reference.
8. **TMJ yes:** masseter tasks must reflect 15min cap, Falim-only, permanent disclaimer in description.
9. **High screen (6+ h):** add screen-forward-head line to midday mewing; optionally second nasal check in afternoon (max 2 nasal/day).
10. **Monthly bone check:** 1st of month at **mewing midday** time.
