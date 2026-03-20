export interface FitmaxModule {
  id: number;
  title: string;
  phase: string;
  duration: string;
  level: string;
  status: 'locked' | 'available' | 'in_progress' | 'complete';
  content: string;
}

// Note: this mirrors the integration spec and keeps module pages as dedicated screens.
export const FITMAX_MODULES: FitmaxModule[] = [
  {
    id: 1,
    title: 'Your Body, Your Baseline',
    phase: 'Foundation',
    duration: '12 min',
    level: 'Beginner',
    status: 'available',
    content: `Personalization Banner: "Your body burns approximately [TDEE] calories per day. Your goal target is [X] calories."

The Scale Is Lying to You
Most people judge their fitness journey by bodyweight alone. Scale fluctuations are often water, food volume, and glycogen shifts.

Key Concept
The goal is body composition: less fat, more muscle.

Fat Mass vs Lean Mass
Fat mass stores energy. Lean mass is metabolically active and includes muscle, bone, organs, and water.

How to Measure Progress
Use trends: scale averages, tape measurements, and progress photos.

Apply It
- Log weight now in Progress.
- Log food for 3 days in chat before changing intake.`,
  },
  {
    id: 2,
    title: 'The Science of Your Goal',
    phase: 'Foundation',
    duration: '15 min',
    level: 'All',
    status: 'available',
    content: `Personalization Banner: "Your daily target: [X] calories from maintenance [TDEE]."

Fat Loss Branch
Fat leaves the body primarily as CO2 and water. Spot reduction is a myth.

Muscle Preservation
Cutting requires protein and resistance training to protect lean mass.

Diet Breaks
Planned maintenance weeks can improve adherence and preserve performance.

Apply It
- Prioritize protein target this week.
- Ask in chat: "what's my workout today?"`,
  },
  {
    id: 3,
    title: 'How Muscle Grows: The Real Biology',
    phase: 'Foundation',
    duration: '14 min',
    level: 'Beginner',
    status: 'available',
    content: `You build muscle after training, during recovery. Training is the signal; sleep and nutrition are construction.

Mechanical tension is primary. Progressive overload is non-negotiable.

Apply It
- Use controlled eccentrics next session.
- Log session feel in chat (great/average/rough).`,
  },
  {
    id: 4,
    title: 'Your Training Split, Decoded',
    phase: 'Foundation',
    duration: '10 min',
    level: 'Beginner',
    status: 'available',
    content: `Your split is built around recovery windows and schedule constraints.

Training frequency and recovery have to be balanced to progress.

Apply It
- Identify first training day.
- Message: "start my workout" when ready.`,
  },
  {
    id: 5,
    title: 'Movement Mastery: The Foundations',
    phase: 'Execution',
    duration: '20 min',
    level: 'Beginner-Intermediate',
    status: 'locked',
    content: `Compound patterns drive the majority of results: squat, hinge, horizontal push/pull, vertical push/pull.

Prioritize range of motion and control over ego loading.

Apply It
- Review form notes before your next lift.
- Film one main compound from the side.`,
  },
  {
    id: 6,
    title: 'Your Exercise Library',
    phase: 'Execution',
    duration: 'Reference',
    level: 'All',
    status: 'locked',
    content: `Searchable movement library for plan exercises, including cues, alternatives, and common mistakes.

Use this before sessions and whenever form quality drops.`,
  },
  {
    id: 7,
    title: 'Intensity, RPE, and Training That Works',
    phase: 'Execution',
    duration: '11 min',
    level: 'Beginner-Intermediate',
    status: 'locked',
    content: `Most people undertrain intensity. RPE and RIR calibrate effort.

Work sets for hypertrophy generally land at RPE 7-9.

Apply It
- Push last compound set to honest RPE 8-9.
- Log fatigue trend in chat weekly.`,
  },
  {
    id: 8,
    title: 'Nutrition Architecture',
    phase: 'Execution',
    duration: '18 min',
    level: 'Beginner-Intermediate',
    status: 'locked',
    content: `Protein target is non-negotiable, with meal distribution supporting MPS.

Carbs fuel performance; fats support hormones.

Apply It
- Log meals in chat.
- Check protein before bed and fill gaps.`,
  },
  {
    id: 9,
    title: 'Cardio: The Full Picture',
    phase: 'Execution',
    duration: '13 min',
    level: 'Beginner-Intermediate',
    status: 'locked',
    content: `Cardio doesn't kill gains when programmed correctly.

Zone 2 supports fat loss and recovery with low interference.

Apply It
- Schedule your weekly cardio blocks in chat.
- Run one Zone 2 session this week.`,
  },
  {
    id: 10,
    title: 'Sleep, Recovery & Hormonal Environment',
    phase: 'Optimization',
    duration: '16 min',
    level: 'Intermediate',
    status: 'locked',
    content: `Sleep is where adaptation occurs. Hormonal profile, appetite control, and recovery all depend on sleep quality.

Set consistent wake and sleep anchors.

Apply It
- Fix wake time for 14 days.
- No screens 30 minutes pre-bed for 7 days.`,
  },
  {
    id: 11,
    title: 'Supplementation: Evidence, Hype, and Stack',
    phase: 'Optimization',
    duration: '18 min',
    level: 'Intermediate-Advanced',
    status: 'locked',
    content: `Tier 1 foundations first: creatine, omega-3, vitamin D/K2, magnesium, caffeine contextually.

Master consistency before advanced compounds.

Apply It
- Start creatine 3-5g daily.
- Add omega-3 and log adherence in chat.`,
  },
  {
    id: 12,
    title: 'Posture, Aesthetics & The Visual Edge',
    phase: 'Optimization',
    duration: '14 min',
    level: 'Intermediate',
    status: 'locked',
    content: `Posture changes visual impact quickly and amplifies existing physique work.

Address APT, UCS, and forward head posture with consistent corrective work.

Apply It
- Run side-view posture assessment.
- Add face pulls as warm-up this week.`,
  },
  {
    id: 13,
    title: 'Plateaus, Adjustments & The Long Game',
    phase: 'Optimization',
    duration: '12 min',
    level: 'Intermediate',
    status: 'locked',
    content: `Plateaus are expected. Use 4-week check-ins: weight trend, measurements, photos, performance, recovery markers.

Adjust one lever at a time.

Apply It
- Send check-in metrics in chat for reassessment.`,
  },
  {
    id: 14,
    title: 'Building the Identity, Not Just the Body',
    phase: 'Identity & Mastery',
    duration: '11 min',
    level: 'All',
    status: 'locked',
    content: `Identity-based behavior sustains results better than outcome obsession.

Use the two-day rule and minimum viable sessions to protect consistency.

Apply It
- Write your identity statement.
- Implement one environment change today.`,
  },
  {
    id: 15,
    title: 'Graduation, What\'s Next & The Full Stack',
    phase: 'Identity & Mastery',
    duration: '10 min',
    level: 'All',
    status: 'locked',
    content: `Review your compounding progress and set a concrete next milestone.

The system continues through iterative goal cycles.

Apply It
- Set next target (weight, PR, measurement, or streak).
- Put a date on it in app.`,
  },
];

export function fitmaxPhaseProgress(modules: FitmaxModule[]) {
  const completed = modules.filter(m => m.status === 'complete').length;
  const currentPhase = modules.find(m => m.status === 'available' || m.status === 'in_progress')?.phase || 'Foundation';
  return {
    currentPhase,
    completed,
    total: modules.length,
    ratio: modules.length ? completed / modules.length : 0,
  };
}
