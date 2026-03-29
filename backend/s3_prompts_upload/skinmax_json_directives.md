## SKINMAX — JSON SCHEDULE OUTPUT (MANDATORY)

1. Use **exact HH:MM** (24h) for every task. Derive all times from wake_time and sleep_time using the reference + COMPUTED ANCHOR TIMES above.
2. **Do NOT** add a generic "morning check-in / let me know you're awake" at wake time for SkinMax — start the day with **AM Routine** at wake+15 (or stagger per MULTI-ACTIVE-MODULES if another module already owns wake).
3. Respect **quiet hours**: no tasks scheduled between sleep_time and wake_time.
4. Keep **3–5 tasks per calendar day**. Minimum daily: AM routine, Midday tip, PM routine. Add SPF reapply / hydration / restriction only when rules say so.
5. **Title + description** must reflect the correct concern protocol (AM steps, PM retinoid vs rest, exfoliation night copy when applicable).
6. On **weekly exfoliation day** (default Wednesday if not in onboarding), PM task = exfoliation routine from reference (not standard PM).
7. **Sunday**: add pillowcase reminder at midday time.
8. **1st of month**: progress photo at midday; routine check-in 30 min after PM time.
9. For `sometimes` outdoor: if outside_today is No, you may still schedule a short "Going outside today?" reminder near AM+3h window or fold into AM description — do **not** schedule SPF reapply unless they would be going out.
10. Use `task_type`: `routine` for AM/PM/exfoliation blocks, `reminder` for SPF/hydration/restriction/pillowcase/photo/check-in style pings.
11. **Midday tip** descriptions must follow the **7-day rotating micro-tip copy** in the SkinMax notification engine reference (match weekday to the correct tip).
12. **No AM chase:** do **not** schedule a follow-up task if the user missed AM — the reference forbids nagging after AM slot + 2h.
13. **Restriction** tasks: max **1/day**; rotate meal slot (wake+1h / +5h / +9h) and rotate which restriction when several are opted in.
