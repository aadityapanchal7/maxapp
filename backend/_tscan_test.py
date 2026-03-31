from models.scan import TripleFullScanResult
import json
r = {
  "psl_score": 7, "psl_tier": "", "potential": 8, "archetype": "Classic", "appeal": 7,
  "ascension_time_months": 6, "age_score": 25, "weakest_link": "x", "aura_tags": [],
  "feature_scores": {
    "eyes": {"score": 5, "tag": "", "notes": ""}, "jaw": {"score": 5, "tag": "", "notes": ""},
    "cheekbones": {"score": 5, "tag": "", "notes": ""}, "chin": {"score": 5, "tag": "", "notes": ""},
    "nose": {"score": 5, "tag": "", "notes": ""}, "lips": {"score": 5, "tag": "", "notes": ""},
    "brow_ridge": {"score": 5, "tag": "", "notes": ""}, "skin": {"score": 5, "tag": "", "notes": ""},
    "hairline": {"score": 5, "tag": "", "notes": ""}, "symmetry": {"score": 5, "tag": "", "notes": ""}
  },
  "proportions": {"facial_thirds": "", "golden_ratio_percent": 0, "bigonial_bizygomatic_ratio": 0, "fwhr": 0},
  "side_profile": {"maxillary_projection": 3.5, "mandibular_projection": 4.1, "gonial_angle": "",
    "submental_angle": "", "ricketts_e_line": "", "forward_head_posture": False},
  "masculinity_index": 5, "mog_percentile": 50, "glow_up_potential": 50,
  "metrics": [{"id": "j", "label": "J", "score": 7, "summary": "s"}],
  "preview_blurb": "", "problems": [], "suggested_modules": []
}
m = TripleFullScanResult.model_validate(r)
print(m.side_profile.maxillary_projection, type(m.side_profile.maxillary_projection).__name__)
