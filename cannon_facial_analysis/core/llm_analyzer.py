import os
from groq import Groq
import json
from typing import Dict, Any

_GROQ_SYSTEM_PROMPT = "You are a helpful assistant that outputs JSON."


def _get_groq_system_prompt() -> str:
    try:
        from services.prompt_loader import PromptKey, resolve_prompt
        return resolve_prompt(PromptKey.GROQ_FACE_ANALYZER, _GROQ_SYSTEM_PROMPT)
    except ImportError:
        return _GROQ_SYSTEM_PROMPT


class LLMAnalyzer:
    def __init__(self):
        # Expects GROQ_API_KEY in environment variables
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        if self.api_key:
            self.client = Groq(api_key=self.api_key)

    def generate_recommendations(self, measurements: Dict[str, Any], golden_ratio_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate looksmaxxing recommendations using Groq LLM.
        """
        if not self.client:
            return {
                "error": "Groq API key not configured. Cannot generate AI recommendations.",
                "recommendations": []
            }

        # Construct a prompt with the analysis data
        prompt = f"""
        Act as an expert aesthetician and looksmaxxing consultant. Analyze the following facial metrics and provide specific, actionable advice to improve facial aesthetics.
        
        Facial Metrics:
        {json.dumps(measurements, indent=2)}
        
        Golden Ratio Analysis:
        {json.dumps(golden_ratio_analysis, indent=2)}
        
        Please provide:
        1. A brief analysis of the user's key strengths.
        2. 3-5 specific, actionable recommendations (e.g., hairstyle, facial hair, mewing, specific exercises, skincare).
        3. Be objective but encouraging.
        
        Format the output as JSON with keys: "strengths" (list), "recommendations" (list of objects with "title" and "description"), "summary" (string).
        """

        try:
            completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": _get_groq_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model="mixtral-8x7b-32768",
                response_format={"type": "json_object"}
            )
            
            response_content = completion.choices[0].message.content
            return json.loads(response_content)
            
        except Exception as e:
            print(f"LLM Error: {e}")
            return {
                "error": f"Failed to generate recommendations: {str(e)}",
                "recommendations": []
            }
