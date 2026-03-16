"""
Gemini Service - LLM for chat and face analysis
Uses Gemini 2.5 Flash with structured outputs
"""

# TODO: Migrate to google-genai as google.generativeai is deprecated
import google.generativeai as genai
from typing import Optional, List
from config import settings
from models.scan import FaceMetrics, ScanAnalysis


# Exhaustive system prompt for face analysis
FACE_ANALYSIS_SYSTEM_PROMPT = """You are an expert facial aesthetics analyst with deep knowledge of:
- Facial proportion theory (golden ratio, facial thirds, fifths)
- Bone structure analysis (jawline, cheekbones, orbital rims)
- Soft tissue assessment (skin, fat distribution, muscle)
- Profile analysis (convexity, angles, projections)
- Sexual dimorphism markers
- Lookmaxxing and facial optimization techniques

You will analyze three photos of a person's face (front, left profile, right profile) and provide an EXHAUSTIVE, detailed analysis covering EVERY aspect of their facial features.

## ANALYSIS REQUIREMENTS:

### 1. JAWLINE ANALYSIS
- Definition score (0-10): How clearly defined is the jawline?
- Gonial angle: Estimate the angle in degrees (ideal male: 120-130°, female: 125-135°)
- Symmetry: Left vs right comparison
- Width-to-face ratio: Is the jaw wide or narrow relative to face?
- Masseter development: Muscle visibility and size
- Chin projection: Forward projection strength
- Chin shape: Pointed, square, round, or cleft
- Ramus length: Vertical jaw branch assessment

### 2. CHEEKBONES ANALYSIS
- Prominence: How projected are the cheekbones?
- Height position: High, medium, or low set
- Bizygomatic width: Face width at cheekbones
- Buccal hollowing: Definition below cheekbones
- Symmetry assessment

### 3. EYE AREA ANALYSIS (CRITICAL)
- Canthal tilt: Positive, neutral, or negative (with degree estimate)
- Interpupillary distance: Close, average, or wide set
- Upper eyelid exposure: Amount of eyelid showing (less is often better)
- Palpebral fissure: Eye opening height
- Eye shape: Almond, round, hooded, monolid, etc.
- Under-eye area: Hollows, bags, dark circles assessment
- Eyebrow position and shape
- Brow bone prominence: Ridge projection
- Orbital rim support: Infraorbital support quality
- Overall eye area symmetry

### 4. NOSE ANALYSIS
- Dorsum shape: Straight, convex, concave, wavy
- Bridge width and height
- Tip shape, projection, and rotation
- Nostril shape and symmetry
- Alar width relative to face
- Nasofrontal angle (at nasion)
- Nasolabial angle (nose to lip)
- Overall harmony with face

### 5. LIPS/MOUTH ANALYSIS
- Upper and lower lip volume
- Lip ratio (ideal ~1:1.6 upper to lower)
- Cupid's bow definition
- Lip width relative to face
- Vermillion border clarity
- Philtrum length and definition
- Symmetry assessment

### 6. FOREHEAD ANALYSIS
- Height (short, average, tall)
- Width and shape
- Hairline shape and position
- Brow bone projection (frontal bossing)
- Temple fullness vs hollowing
- Skin texture in this area

### 7. SKIN ANALYSIS
- Overall quality score
- Skin type (normal, oily, dry, combination, sensitive)
- Texture smoothness
- Clarity (blemishes, spots)
- Tone evenness
- Hydration appearance
- Pore visibility
- Acne presence and scarring
- Hyperpigmentation
- Under-eye darkness
- Signs of aging
- Sun damage

### 8. FACIAL PROPORTIONS
- Face shape classification
- Facial thirds balance (upper/middle/lower)
- Horizontal fifths assessment
- Overall symmetry percentage
- FWHR (Facial Width-to-Height Ratio) estimate
- Profile type (convex/straight/concave)
- Golden ratio adherence score

### 9. PROFILE ANALYSIS (from side photos)
- Forehead projection
- Nose projection from face
- Lip projection relative to nose-chin line
- Chin projection
- Neck-chin angle
- Submental (under chin) definition
- Gonial angles from both sides
- Ear position relative to face
- Overall profile harmony

### 10. HAIR ANALYSIS
- Density/fullness
- Hairline health
- Recession level
- Crown thinning
- Hair quality/texture
- Style suitability recommendations

### 11. BODY FAT INDICATORS (from face)
- Facial leanness
- Buccal fat level
- Submental fat
- Jowl presence
- Definition potential with fat loss
- Estimated body fat range

## OUTPUT FORMAT:
Provide your analysis as a structured JSON matching the FaceMetrics schema exactly.
Include:
- Numerical scores (0-10) for all quantifiable metrics
- Descriptive assessments for qualitative features
- Specific, actionable improvement suggestions
- Recommended courses based on findings
- Confidence score for your analysis

Be thorough but honest. Do not make medical claims. Focus on actionable improvements.
"""

# Chat system prompt for Cannon persona
CANNON_CHAT_SYSTEM_PROMPT = """You are Cannon, the founder and lead coach of the Cannon Lookmaxxing app. You are a charismatic, knowledgeable, and supportive influencer who helps people improve their appearance and confidence.

## YOUR PERSONALITY:
- Direct and honest, but encouraging
- Passionate about self-improvement
- Knowledgeable about fitness, skincare, facial optimization, and mindset
- You use modern, casual language but remain professional
- You celebrate user wins and progress
- You're firm about consistency and discipline

## YOUR EXPERTISE AREAS:

### 1. JAWLINE OPTIMIZATION
- Mewing (proper tongue posture)
- Chewing exercises (mastic gum, falim gum)
- Jaw muscle training
- Posture impact on jawline
- Realistic expectations and timelines

### 2. BODY COMPOSITION
- Fat loss strategies for facial definition
- Macro nutrition basics
- Training recommendations
- Water retention management
- Body recomposition for face gains

### 3. SKINCARE
- Cleansing, moisturizing, SPF basics
- Tretinoin and retinoids
- Vitamin C, niacinamide, etc.
- Acne management
- Anti-aging prevention
- Product recommendations

### 4. HAIR OPTIMIZATION
- Hair care routines
- Minoxidil and finasteride info (non-medical)
- Styling tips for face shape
- Hairline maintenance

### 5. POSTURE & BODY LANGUAGE
- Forward head posture correction
- Shoulder positioning
- Confidence body language
- Exercise routines for posture

### 6. MINDSET & CONFIDENCE
- Building self-confidence
- Dealing with insecurity
- Progress mindset
- Social skills basics

## IMPORTANT RULES:
1. NEVER make medical claims or diagnose conditions
2. NEVER recommend surgery as a first option
3. Always emphasize natural, lifestyle-based improvements first
4. Be encouraging but realistic about timelines
5. Recommend the app's courses when relevant
6. Keep responses focused and actionable
7. If user shares struggles, be empathetic but redirect to solutions
8. Use the user's scan history if available for personalized advice

## SCHEDULE MANAGEMENT:
You can directly modify the user's active schedule if they ask for changes (e.g., "I'm busy tomorrow morning", "Move my workout to 6pm", "Add more facial exercises").
When the user asks for such changes, use the `modify_schedule` tool.
Always confirm with the user after you've successfully requested a schedule modification.

## MAXX SCHEDULE ONBOARDING:
When a user wants to start a maxx schedule (e.g. "I want to start my SkinMax schedule" or the system tells you they initiated it from the app), follow this EXACT conversational flow:
1. Greet them warmly and explain what the schedule does for that maxx type.
2. Ask: "What time do you usually wake up?" — wait for their answer.
3. Ask: "What time do you usually go to sleep?" — wait for their answer.
4. Ask: "Are you planning to be outside much today?" — wait for their answer.
5. Once you have wake_time, sleep_time, and outside_today, call the `generate_maxx_schedule` tool with those values plus the maxx_id.
6. After the schedule is generated, confirm it and give them a brief overview of their daily routine.

IMPORTANT: Ask these questions ONE AT A TIME. Do NOT ask all at once. Be conversational and natural.

## WAKE-UP DETECTION:
If the user says "I'm awake", "im awake", "just woke up", or similar wake-up phrases:
- Acknowledge it enthusiastically
- Remind them it's time for their AM routine
- Ask if they'll be going outside today (for sunscreen reapply reminders)
- If they say yes to going outside, note it for sunscreen reminders every 3 hours

## CONTEXT:
You have access to the user's:
- Face scan results and scores
- Current courses and progress
- Current active schedule details (including maxx schedules)
- Chat history for context
- Onboarding data (skin type, goals, etc.)

Remember: You're building a community of people committed to becoming their best selves. Every interaction should motivate and guide them forward.
"""


def modify_schedule(feedback: str):
    """
    Modifies the user's active schedule based on natural language feedback.
    Use this when the user asks to change, move, add, or remove tasks from their schedule.
    
    Args:
        feedback: The natural language description of the requested changes.
    """
    return {"status": "success", "message": f"Successfully requested schedule adaptation with feedback: {feedback}"}


def generate_maxx_schedule(maxx_id: str, wake_time: str, sleep_time: str, outside_today: bool):
    """
    Generates a personalised maxx schedule for the user based on their preferences.
    Call this after asking the user for their wake time, sleep time, and whether they'll be outside.
    
    Args:
        maxx_id: The maxx type ID, e.g. 'skinmax', 'hairmax', 'fitmax'.
        wake_time: User's wake time in HH:MM 24-hour format, e.g. '07:00'.
        sleep_time: User's sleep time in HH:MM 24-hour format, e.g. '23:00'.
        outside_today: Whether the user plans to be outside today (for sunscreen reminders).
    """
    return {
        "status": "success",
        "message": f"Generating {maxx_id} schedule: wake={wake_time}, sleep={sleep_time}, outside={outside_today}"
    }


def update_schedule_context(key: str, value: str):
    """
    Updates a piece of context about the user's schedule patterns.
    Use this to store information the user tells you about their habits.
    
    Args:
        key: The context key, e.g. 'actual_wake_time', 'outside_today', 'skin_concern'.
        value: The value to store.
    """
    return {"status": "success", "message": f"Context updated: {key}={value}"}


class GeminiService:
    """Gemini LLM service for face analysis and chat"""
    
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(
            settings.gemini_model,
            tools=[modify_schedule, generate_maxx_schedule, update_schedule_context]
        )
        self.vision_model = genai.GenerativeModel(settings.gemini_model)
    
    async def analyze_face(
        self,
        front_image: bytes,
        left_image: bytes,
        right_image: bytes
    ) -> ScanAnalysis:
        """
        Analyze face images using Gemini with structured output
        Uses fallback if structured output fails
        """
        try:
            # Prepare images
            images = [
                {"mime_type": "image/jpeg", "data": front_image},
                {"mime_type": "image/jpeg", "data": left_image},
                {"mime_type": "image/jpeg", "data": right_image}
            ]
            
            # Create prompt with images
            prompt_parts = [
                FACE_ANALYSIS_SYSTEM_PROMPT,
                "\n\n## IMAGES TO ANALYZE:\n",
                "FRONT VIEW:",
                images[0],
                "\nLEFT PROFILE:",
                images[1],
                "\nRIGHT PROFILE:",
                images[2],
                "\n\nProvide your complete analysis as JSON matching the ScanAnalysis schema."
            ]
            
            # Try structured output first
            try:
                response = await self._generate_structured_response(prompt_parts)
                return ScanAnalysis.model_validate_json(response)
            except Exception as struct_error:
                print(f"Structured output failed, using fallback: {struct_error}")
                return await self._analyze_face_fallback(prompt_parts)
                
        except Exception as e:
            print(f"Face analysis error: {e}")
            # Return default analysis on complete failure
            return self._get_default_analysis()
    
    async def _generate_structured_response(self, prompt_parts: list) -> str:
        """Generate response with structured output config"""
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=ScanAnalysis
        )
        
        response = self.vision_model.generate_content(
            prompt_parts,
            generation_config=generation_config
        )
        
        return response.text
    
    async def _analyze_face_fallback(self, prompt_parts: list) -> ScanAnalysis:
        """Fallback method without strict schema enforcement"""
        # Add explicit JSON instruction
        fallback_prompt = prompt_parts + [
            "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanations."
        ]
        
        response = self.vision_model.generate_content(fallback_prompt)
        
        # Try to parse the response
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        return ScanAnalysis.model_validate_json(text)
    
    def _get_default_analysis(self) -> ScanAnalysis:
        """Return a default analysis when all methods fail"""
        from models.scan import (
            FaceMetrics, JawlineMetrics, CheekbonesMetrics, EyeAreaMetrics,
            NoseMetrics, LipsMetrics, ForeheadMetrics, SkinMetrics,
            FacialProportions, ProfileMetrics, HairMetrics, BodyFatIndicators,
            ImprovementSuggestion, ImprovementPriority
        )
        
        default_metrics = FaceMetrics(
            overall_score=5.0,
            harmony_score=5.0,
            jawline=JawlineMetrics(
                definition_score=5.0, symmetry_score=5.0, masseter_development=5.0,
                chin_projection=5.0, ramus_length=5.0
            ),
            cheekbones=CheekbonesMetrics(
                prominence_score=5.0, width_score=5.0, hollowness_below=5.0, symmetry_score=5.0
            ),
            eye_area=EyeAreaMetrics(
                upper_eyelid_exposure=5.0, palpebral_fissure_height=5.0, under_eye_area=5.0,
                brow_bone_prominence=5.0, orbital_rim_support=5.0, symmetry_score=5.0
            ),
            nose=NoseMetrics(
                bridge_height=5.0, tip_projection=5.0, nostril_symmetry=5.0, overall_harmony=5.0
            ),
            lips=LipsMetrics(
                upper_lip_volume=5.0, lower_lip_volume=5.0, cupids_bow_definition=5.0,
                vermillion_border=5.0, philtrum_definition=5.0, lip_symmetry=5.0
            ),
            forehead=ForeheadMetrics(
                brow_bone_projection=5.0, temple_hollowing=5.0, forehead_symmetry=5.0, skin_texture=5.0
            ),
            skin=SkinMetrics(
                overall_quality=5.0, texture_score=5.0, clarity_score=5.0, tone_evenness=5.0,
                hydration_appearance=5.0, pore_visibility=5.0, under_eye_darkness=5.0
            ),
            proportions=FacialProportions(
                facial_thirds_balance=5.0, upper_third_score=5.0, middle_third_score=5.0,
                lower_third_score=5.0, horizontal_fifths_balance=5.0, overall_symmetry=5.0,
                facial_convexity=5.0, golden_ratio_adherence=5.0
            ),
            profile=ProfileMetrics(
                forehead_projection=5.0, nose_projection=5.0, lip_projection=5.0,
                chin_projection=5.0, submental_area=5.0, ramus_visibility=5.0, profile_harmony=5.0
            ),
            hair=HairMetrics(density=5.0, hairline_health=5.0, hair_quality=5.0),
            body_fat=BodyFatIndicators(facial_leanness=5.0, definition_potential=5.0),
            confidence_score=0.5,
            image_quality_front=5.0,
            image_quality_left=5.0,
            image_quality_right=5.0
        )
        
        return ScanAnalysis(
            metrics=default_metrics,
            improvements=[
                ImprovementSuggestion(
                    area="general",
                    priority=ImprovementPriority.MEDIUM,
                    current_score=5.0,
                    potential_score=7.0,
                    suggestion="Analysis could not be completed. Please try again with clearer photos.",
                    exercises=[],
                    products=[],
                    timeframe=""
                )
            ],
            top_strengths=[],
            focus_areas=["Image quality"],
            recommended_courses=[],
            personalized_summary="We encountered an issue analyzing your photos. Please ensure good lighting and clear face visibility.",
            estimated_potential=6.0
        )
    
    async def chat(
        self,
        message: str,
        chat_history: List[dict],
        user_context: Optional[dict] = None,
        image_data: Optional[bytes] = None
    ) -> str:
        """
        Chat with Cannon persona
        Uses conversation history for context, supports vision
        """
        # Build context from user data
        context_str = ""
        if user_context:
            if user_context.get("latest_scan"):
                scan = user_context["latest_scan"]
                context_str += f"\n\nUser's latest face scan score: {scan.get('overall_score', 'N/A')}/10"
                if scan.get("focus_areas"):
                    context_str += f"\nFocus areas: {', '.join(scan['focus_areas'])}"

            if user_context.get("onboarding"):
                ob = user_context["onboarding"]
                parts = []
                if ob.get("skin_type"):
                    parts.append(f"Skin type: {ob['skin_type']}")
                if ob.get("goals"):
                    parts.append(f"Goals: {', '.join(ob['goals'])}")
                if ob.get("gender"):
                    parts.append(f"Gender: {ob['gender']}")
                if ob.get("age"):
                    parts.append(f"Age: {ob['age']}")
                if parts:
                    context_str += f"\n\nUser profile: {', '.join(parts)}"

            if user_context.get("current_course"):
                course = user_context["current_course"]
                context_str += f"\n\nCurrent course: {course.get('title', 'N/A')}"
                context_str += f"\nProgress: {course.get('progress_percentage', 0)}%"

            if user_context.get("active_schedule"):
                schedule = user_context["active_schedule"]
                stype = schedule.get("schedule_type", "course")
                label = schedule.get("course_title") or schedule.get("maxx_id") or "Unknown"
                context_str += f"\n\nUser's Active Schedule ({stype}): {label}"
                if schedule.get("schedule_context"):
                    ctx = schedule["schedule_context"]
                    context_str += f"\nSchedule context: wake={ctx.get('wake_time')}, sleep={ctx.get('sleep_time')}, skin_concern={ctx.get('skin_concern')}"
                for i, day in enumerate(schedule.get("days", [])[:3]):
                    context_str += f"\nDay {day.get('day_number')}: {len(day.get('tasks', []))} tasks"
                    for t in day.get("tasks", []):
                        context_str += f"\n  - {t.get('time')} {t.get('title')} ({t.get('status')})"

            if user_context.get("active_maxx_schedule"):
                ms = user_context["active_maxx_schedule"]
                context_str += f"\n\nUser already has an active {ms.get('maxx_id')} schedule (created {ms.get('created_at')})."
        
        # Build chat prompt
        chat_prompt = CANNON_CHAT_SYSTEM_PROMPT
        if context_str:
            chat_prompt += f"\n\n## USER CONTEXT:{context_str}"
        
        # Format history
        history_for_gemini = []
        
        # Add system instruction
        # Note: GenerativeModel.start_chat doesn't support a separate system role easily in this SDK version
        # We prepend it to the first message or use it as a preamble
        
        for msg in chat_history[-15:]:  # Last 15 messages for context
            role = "user" if msg["role"] == "user" else "model"
            # Handle historical attachments if they were images (simplified to just text for history)
            content = msg["content"]
            history_for_gemini.append({"role": role, "parts": [content]})

        # If history is empty, add the system prompt as a user message
        if not history_for_gemini:
            history_for_gemini.append({"role": "user", "parts": [chat_prompt]})
            history_for_gemini.append({"role": "model", "parts": ["Yo! I'm Cannon. I've got your context. What's up?"]})
        else:
            # Inject system prompt into the first message of the session
            history_for_gemini[0]["parts"][0] = f"{chat_prompt}\n\n{history_for_gemini[0]['parts'][0]}"
        
        # Add new message (with image if provided)
        new_message_parts = []
        if image_data:
            new_message_parts.append({"mime_type": "image/jpeg", "data": image_data})
        
        new_message_parts.append(message if message else "Look at this image.")
        
        # Generate response
        chat = self.model.start_chat(history=history_for_gemini)
        response = chat.send_message(new_message_parts)
        
        # Handle tool calls
        tool_calls = []
        response_text = ""
        
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                tool_calls.append({
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args)
                })
            elif hasattr(part, 'text') and part.text:
                response_text += part.text
        
        return {
            "text": response_text.strip() or "I've processed your request.",
            "tool_calls": tool_calls
        }


# Singleton instance
gemini_service = GeminiService()
