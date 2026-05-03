"""Few-shot generation examples per max.

Two short examples per max, presented as compressed templates. They
exist to teach the model the OUTPUT STYLE (cadence, intensity ramp,
descriptive overrides, modifier honoring) — not specific content.

Examples are selected based on user state to maximize relevance. If
no targeted match, the default pair is returned.
"""

from __future__ import annotations

from typing import Any

# Each example is a fully-formed JSON-ish snippet (rendered as text in the
# prompt). Compact deliberately — long examples eat tokens and hurt latency.

_SKINMAX_EXAMPLES = {
    "pigmentation_stable": """
INPUT: skin_concern=pigmentation, barrier_state=stable, skin_type=combo, wake=06:30, sleep=23:00
OUTPUT (excerpt):
{
  "days": [
    { "day_index": 0, "tasks": [
        {"catalog_id":"skin.cleanse_am","time":"06:45","title":"cleanse AM","description":"gentle cleanser, lukewarm — barrier-first week 1"},
        {"catalog_id":"skin.moisturize_am","time":"06:50","title":"ceramides AM","description":"ceramide moisturizer on damp skin"},
        {"catalog_id":"skin.spf","time":"06:55","title":"spf 50","description":"non-negotiable for pigment recovery"},
        {"catalog_id":"skin.cleanse_pm","time":"22:15","title":"cleanse PM"},
        {"catalog_id":"skin.moisturize_pm","time":"22:20","title":"ceramides PM"}
      ]
    },
    { "day_index": 7, "tasks": [
        {"catalog_id":"skin.cleanse_am","time":"06:45","title":"cleanse AM"},
        {"catalog_id":"skin.azelaic_am","time":"06:50","title":"azelaic AM","description":"azelaic 15% — anti-inflammatory + brightening"},
        {"catalog_id":"skin.moisturize_am","time":"06:55","title":"ceramides AM"},
        {"catalog_id":"skin.spf","time":"07:00","title":"spf 50"},
        {"catalog_id":"skin.cleanse_pm","time":"21:30","title":"cleanse PM"},
        {"catalog_id":"skin.retinoid_pm","time":"21:45","title":"tret pea PM","description":"0.05% pea-sized on dry skin, wait 5min before moisturizer"},
        {"catalog_id":"skin.moisturize_pm","time":"21:55","title":"ceramides PM"}
      ]
    }
  ],
  "summary": "Week 1 = repair (cleanse + ceramides + spf only). Week 2 introduces azelaic AM and tret PM on alternating nights with dermastamp."
}
""".strip(),

    "rosacea_damaged": """
INPUT: skin_concern=rosacea, barrier_state=damaged, skin_type=normal, wake=07:00, sleep=23:00
OUTPUT (excerpt):
{
  "days": [
    { "day_index": 0, "tasks": [
        {"catalog_id":"skin.cleanse_am","time":"07:15","title":"cleanse AM","description":"gentle, no scrubbing — calming first"},
        {"catalog_id":"skin.centella_am","time":"07:20","title":"centella AM","description":"centella for redness reduction during repair"},
        {"catalog_id":"skin.moisturize_am","time":"07:25","title":"ceramides AM"},
        {"catalog_id":"skin.spf","time":"07:30","title":"spf 50","description":"physical SPF preferred for sensitivity"},
        {"catalog_id":"skin.cleanse_pm","time":"22:00","title":"cleanse PM"},
        {"catalog_id":"skin.centella_am","time":"22:05","title":"centella PM"},
        {"catalog_id":"skin.moisturize_pm","time":"22:10","title":"ceramides PM"},
        {"catalog_id":"skin.barrier_pause","time":"22:15","title":"actives off today"}
      ]
    }
  ],
  "summary": "REPAIR phase: NO actives, NO retinoid. Centella + ceramides + spf only. Re-evaluate at day 14."
}
""".strip(),
}

_HAIRMAX_EXAMPLES = {
    "loss_active_curly": """
INPUT: hair_type=curly, hair_loss_signs=yes_active, scalp_state=normal, daily_styling=true, dermaroller_owned=true, wake=06:30, sleep=23:30
OUTPUT (excerpt):
{
  "days": [
    { "day_index": 0, "tasks": [
        {"catalog_id":"hair.shampoo_wash","time":"06:50","title":"wash + condition"},
        {"catalog_id":"hair.leavein","time":"07:00","title":"leave-in"},
        {"catalog_id":"hair.style_product","time":"07:05","title":"curl cream + style"},
        {"catalog_id":"hair.minoxidil_am","time":"07:15","title":"minox AM","description":"1ml topical to thinning areas, dry scalp"}
      ]
    },
    { "day_index": 3, "tasks": [
        {"catalog_id":"hair.style_product","time":"07:05","title":"curl cream"},
        {"catalog_id":"hair.minoxidil_am","time":"07:15","title":"minox AM"},
        {"catalog_id":"hair.minoxidil_pm","time":"22:30","title":"minox PM"}
      ]
    },
    { "day_index": 6, "tasks": [
        {"catalog_id":"hair.style_product","time":"07:05","title":"curl cream"},
        {"catalog_id":"hair.cowash_curly","time":"07:00","title":"co-wash midweek"},
        {"catalog_id":"hair.microneedle_pm","time":"21:30","title":"microneedle 0.5mm","description":"4 passes per zone — NO minox today, 24hr gap"}
      ]
    }
  ],
  "summary": "Curly schedule: 1 shampoo + 1 co-wash per week. Minox AM daily, PM 3-4×/wk. Microneedle ONCE on a no-minox day. Style product daily."
}
""".strip(),
}

_HEIGHTMAX_EXAMPLES = {
    "teen_growth_posture": """
INPUT: age=16, heightmax_focus=all, posture_issues=true, training_status=yes_some, wake=07:00, sleep=22:30
OUTPUT (excerpt):
{
  "days": [
    { "day_index": 0, "tasks": [
        {"catalog_id":"height.am_mobility","time":"07:15","title":"5min AM mobility"},
        {"catalog_id":"height.wall_posture","time":"07:25","title":"wall posture 60s"},
        {"catalog_id":"height.sunlight_am","time":"07:30","title":"sunlight 10min","description":"morning sunlight — circadian + vit D"},
        {"catalog_id":"height.desk_reset_midday","time":"13:00","title":"desk reset 5min"},
        {"catalog_id":"height.protein_check","time":"13:15","title":"protein hit"},
        {"catalog_id":"height.pm_decompression","time":"21:30","title":"decompression 5min"},
        {"catalog_id":"height.sleep_extend","time":"22:15","title":"lights out 22:30","description":"teens: 8-10hr — supports growth foundations"}
      ]
    }
  ],
  "summary": "Growth-foundations active (under-18). Posture work AM + midday + PM. Sleep + protein + sunlight as foundation. Frame language: supports natural growth, never promises height."
}
""".strip(),

    "adult_perceived": """
INPUT: age=27, heightmax_focus=perceived, posture_issues=true, training_status=yes_regular, wake=07:30, sleep=23:00
OUTPUT (excerpt):
{
  "days": [
    { "day_index": 0, "tasks": [
        {"catalog_id":"height.am_mobility","time":"07:45","title":"5min AM mobility"},
        {"catalog_id":"height.outfit_check","time":"07:55","title":"outfit proportions","description":"high-waist or tucked, slim/straight, low-contrast shoe/pant"},
        {"catalog_id":"height.shoe_audit","time":"08:00","title":"thicker-soled shoe today"},
        {"catalog_id":"height.desk_reset_midday","time":"13:00","title":"desk reset 5min"},
        {"catalog_id":"height.dead_hang","time":"21:00","title":"dead hang 60s","description":"temporary spinal decompression"},
        {"catalog_id":"height.pm_decompression","time":"22:00","title":"decompression 5min"}
      ]
    }
  ],
  "summary": "Adult — growth track inactive. Posture + retention + perceived (fashion + shoes). Daily desk reset, hang 4×/wk."
}
""".strip(),
}


def few_shot_for(maxx_id: str, user_state: dict[str, Any]) -> str:
    """Pick the most relevant example pair for this user state."""
    if maxx_id == "skinmax":
        if str(user_state.get("barrier_state") or "").lower() == "damaged" \
                or str(user_state.get("skin_concern") or "").lower() == "rosacea":
            return _SKINMAX_EXAMPLES["rosacea_damaged"]
        return _SKINMAX_EXAMPLES["pigmentation_stable"]

    if maxx_id == "hairmax":
        return _HAIRMAX_EXAMPLES["loss_active_curly"]

    if maxx_id == "heightmax":
        try:
            age = int(user_state.get("age") or 0)
        except (TypeError, ValueError):
            age = 0
        if age and age < 22:
            return _HEIGHTMAX_EXAMPLES["teen_growth_posture"]
        return _HEIGHTMAX_EXAMPLES["adult_perceived"]

    return "(no examples for this max yet — produce a minimal viable schedule from the catalog)"
