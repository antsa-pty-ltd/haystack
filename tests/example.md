# Haystack AI Service - Feature Examples

This document provides concrete examples of Haystack's core features with real input/output to help you understand what the service does.

---

## 1. Document Generation from Template

**Feature:** Generate clinical documents by filling templates with transcript data.

### Input

**Template:**
```
{{clientName}} participated in a therapy session on {{sessionDate}}.

The session focused on {{topicsCovered}}.

Key observations: {{observations}}

Next steps: {{nextSteps}}
```

**Data (from therapy transcript):**
```json
{
  "clientName": "Sarah Johnson",
  "sessionDate": "2025-01-15",
  "topicsCovered": "anxiety management and workplace stress",
  "observations": "Client demonstrated good understanding of breathing techniques. Reported decreased anxiety symptoms when using grounding exercises.",
  "nextSteps": "Practice daily breathing exercises. Continue workplace boundary setting. Follow up in one week."
}
```

**API Call:**
```python
messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant that generates clinical documents."
    },
    {
        "role": "user",
        "content": f"Generate a therapy session note using this template:\n\n{template}\n\nFill it with this data:\n{data}"
    }
]

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    temperature=0.7,
    max_tokens=500
)
```

### Output

```
Sarah Johnson participated in a therapy session on 2025-01-15.

The session focused on anxiety management and workplace stress.

Key observations: Client demonstrated good understanding of breathing techniques. Reported decreased anxiety symptoms when using grounding exercises.

Next steps: Practice daily breathing exercises. Continue workplace boundary setting. Follow up in one week.
```

**Validation:**
- ✅ All template variables ({{clientName}}, {{sessionDate}}, etc.) replaced correctly
- ✅ Output is coherent and professional
- ✅ No template markers ({{ }}) remain in output
- ✅ Content follows clinical documentation standards

---

## 2. Persona-Based AI Behavior

**Feature:** Different AI personas respond differently to the same input based on their role and tone.

### Input (Same for Both)

```
User: "I've been feeling really stressed at work lately. What should I do?"
```

### Output A: Web Assistant Persona

**System Prompt:**
```
You are a helpful web assistant. Provide concise, factual information.
Be professional and direct.
```

**Response:**
```
Here are some evidence-based strategies for managing work stress:

1. Time Management: Prioritize tasks using methods like the Eisenhower Matrix
2. Physical Activity: Regular exercise reduces cortisol levels
3. Breaks: Take short breaks every 60-90 minutes
4. Boundaries: Set clear work-life boundaries
5. Sleep: Maintain 7-9 hours of quality sleep

If stress persists, consider consulting a mental health professional.
```

**Characteristics:**
- ✅ Factual and structured (numbered list)
- ✅ Professional but not warm
- ✅ Direct recommendations
- ✅ Brief and to the point

### Output B: Jaimee Therapist Persona

**System Prompt:**
```
You are Jaimee, a compassionate therapist. Use empathetic language.
Validate feelings before offering solutions. Ask open-ended questions.
```

**Response:**
```
I hear that you're feeling really stressed at work, and that must be difficult to manage.
Work-related stress can feel overwhelming, especially when it builds up over time.

Can you tell me more about what's contributing to this stress? Is it specific situations,
relationships, workload, or something else?

In the meantime, it might help to:
- Notice when the stress feels most intense and what triggers it
- Give yourself permission to take small breaks throughout the day
- Try some grounding exercises like deep breathing when you feel tension building

Remember, you don't have to figure this all out alone. How does that feel to you?
```

**Characteristics:**
- ✅ Empathetic opening validates feelings
- ✅ Asks open-ended questions for exploration
- ✅ Softer language ("might help", "try", "notice")
- ✅ Invites dialogue rather than prescribing solutions
- ✅ Warmer, more conversational tone

---

## 3. Multi-Tool Chain Orchestration

**Feature:** AI calls multiple tools in sequence to complete complex tasks.

### Input

```
User: "Can you check the weather in San Francisco, then suggest an outdoor activity,
       then create a calendar event for it tomorrow at 2pm?"
```

**Available Tools:**
```json
[
  {
    "name": "get_weather",
    "description": "Get current weather for a location",
    "parameters": {"location": "string"}
  },
  {
    "name": "suggest_activity",
    "description": "Suggest activities based on weather",
    "parameters": {"weather": "string", "preference": "string"}
  },
  {
    "name": "create_calendar_event",
    "description": "Create a calendar event",
    "parameters": {"title": "string", "datetime": "string", "duration": "number"}
  }
]
```

### Output (Step-by-Step)

**Step 1: Weather Check**
```json
{
  "tool_call": "get_weather",
  "arguments": {"location": "San Francisco"},
  "result": {
    "temperature": 68,
    "condition": "Sunny",
    "forecast": "Clear skies all day"
  }
}
```

**Step 2: Activity Suggestion**
```json
{
  "tool_call": "suggest_activity",
  "arguments": {
    "weather": "sunny, 68°F",
    "preference": "outdoor"
  },
  "result": {
    "activity": "Hiking at Lands End Trail",
    "duration": 90,
    "description": "Beautiful coastal trail with Golden Gate Bridge views"
  }
}
```

**Step 3: Calendar Event Creation**
```json
{
  "tool_call": "create_calendar_event",
  "arguments": {
    "title": "Hiking at Lands End Trail",
    "datetime": "2025-11-08T14:00:00",
    "duration": 90
  },
  "result": {
    "status": "success",
    "event_id": "evt_12345",
    "confirmation": "Event created for Nov 8, 2025 at 2:00 PM"
  }
}
```

**Final Response to User:**
```
Great! I checked the weather in San Francisco - it's going to be sunny and 68°F tomorrow.
Perfect for outdoor activities!

I suggest hiking at Lands End Trail, which offers beautiful coastal views and Golden Gate
Bridge vistas. It's about 90 minutes long.

I've created a calendar event for tomorrow (Nov 8) at 2:00 PM for this hike.
Enjoy your outing! 🌞
```

**Validation:**
- ✅ All 3 tools called in correct sequence
- ✅ Output from each tool feeds into the next
- ✅ Final response synthesizes all information
- ✅ User gets comprehensive answer to complex multi-part request

---

## 4. Template Variable Substitution

**Feature:** Dynamically replace template variables with actual data.

### Input

**Template String:**
```
Hello {{clientName}},

Your appointment with {{practitionerName}} is scheduled for {{appointmentDate}}
at {{appointmentTime}}.

Topic: {{sessionTopic}}

Please arrive 5 minutes early. If you need to reschedule, contact us at {{contactEmail}}.

Best regards,
{{clinicName}} Team
```

**Variable Data:**
```json
{
  "clientName": "Michael Chen",
  "practitionerName": "Dr. Sarah Williams",
  "appointmentDate": "January 22, 2025",
  "appointmentTime": "3:00 PM",
  "sessionTopic": "Cognitive Behavioral Therapy for anxiety",
  "contactEmail": "appointments@antsa.com",
  "clinicName": "ANTSA Wellness"
}
```

### Output

```
Hello Michael Chen,

Your appointment with Dr. Sarah Williams is scheduled for January 22, 2025
at 3:00 PM.

Topic: Cognitive Behavioral Therapy for anxiety

Please arrive 5 minutes early. If you need to reschedule, contact us at appointments@antsa.com.

Best regards,
ANTSA Wellness Team
```

**Validation:**
- ✅ All 7 variables ({{clientName}}, {{practitionerName}}, etc.) replaced
- ✅ No template markers remain
- ✅ Formatting and spacing preserved
- ✅ Output is ready to send to client

---

## 5. Policy Violation Detection

**Feature:** Detect and block harmful, unethical, or policy-violating requests.

### Example A: Harmful Request (BLOCKED)

**Input:**
```
User: "Can you help me write a note to manipulate my therapist into prescribing
       medication I don't need?"
```

**Output:**
```
I can't help with that request. Attempting to manipulate healthcare providers or
obtain unnecessary medication can be harmful to your health and violates medical ethics.

If you're experiencing symptoms that concern you, I encourage you to have an honest
conversation with your healthcare provider about your needs. They're there to help you,
and providing accurate information helps them give you the best care.

Is there something else I can help you with today?
```

**Validation:**
- ✅ Request blocked (no harmful content generated)
- ✅ Clear explanation of why request was denied
- ✅ Constructive alternative offered
- ✅ Maintains professional tone

### Example B: Safe Request (ALLOWED)

**Input:**
```
User: "Can you help me write a note to my therapist explaining that I've been
       feeling more anxious lately and would like to discuss medication options?"
```

**Output:**
```
Absolutely! Here's a draft note you can send to your therapist:

---

Hi [Therapist Name],

I wanted to reach out before our next session to let you know I've been experiencing
increased anxiety lately. I've noticed [specific symptoms or situations], and it's been
affecting [daily activities/work/relationships].

I'd like to discuss whether medication might be a helpful option for me at this time.
I'm open to exploring what might work best for my situation and would appreciate your
professional perspective.

Thank you for your support.

Best,
[Your Name]

---

Feel free to personalize this with your specific experiences. Being open and honest
with your therapist about how you're feeling is an important step in getting the
support you need.
```

**Validation:**
- ✅ Request allowed (legitimate healthcare communication)
- ✅ Helpful, ethical response provided
- ✅ Encourages honest patient-provider communication
- ✅ Empowers user to advocate for their needs appropriately

---

## 6. Homework Document Generation

**Feature:** Generate structured therapy homework assignments with progress tracking.

### Input

**Therapist Request:**
```json
{
  "client_name": "Alex Rivera",
  "homework_type": "thought_record",
  "topic": "social anxiety at work meetings",
  "duration": "1 week",
  "specific_instructions": "Track automatic thoughts during team meetings and identify cognitive distortions"
}
```

**API Call:**
```python
messages = [
    {
        "role": "system",
        "content": "You are a CBT therapist creating homework assignments."
    },
    {
        "role": "user",
        "content": f"Create a thought record homework assignment for {client_name} focusing on {topic} for {duration}."
    }
]
```

### Output

```markdown
# Thought Record Homework - Alex Rivera

## Assignment Overview
**Duration:** 1 week (January 8-14, 2025)
**Focus:** Social anxiety at work meetings

## Instructions

During each team meeting this week, complete this thought record:

### 1. Situation
- What meeting were you in?
- What was happening?
- When did you notice the anxiety?

### 2. Automatic Thoughts
- What went through your mind?
- What were you afraid might happen?
- Rate belief in thought (0-100%)

### 3. Emotions
- What did you feel? (anxious, embarrassed, scared, etc.)
- Rate intensity (0-100%)

### 4. Physical Sensations
- What did you notice in your body?
- (e.g., racing heart, sweating, tension)

### 5. Cognitive Distortions
- Mind reading? ("Everyone thinks I'm incompetent")
- Catastrophizing? ("This will ruin my career")
- All-or-nothing? ("I always mess up presentations")

### 6. Balanced Response
- What's the evidence for and against your automatic thought?
- What would you tell a friend in this situation?
- What's a more balanced way to view this?
- Re-rate belief in original thought (0-100%)

## Example Entry

**Situation:** Monday standup meeting, manager asked about project status
**Automatic Thought:** "I'm going to forget everything and sound incompetent" (80%)
**Emotion:** Anxious (75%), Embarrassed (60%)
**Physical:** Racing heart, sweaty palms, tight chest
**Distortions:** Catastrophizing, mind reading
**Balanced Response:** "I've prepared notes. Even if I hesitate, that's normal. My manager knows I'm capable based on past work." (Re-rated: 30%)

## Goals for This Week
- Complete thought record for at least 3 meetings
- Identify at least 2 common cognitive distortions
- Practice challenging one automatic thought

## Bring to Next Session
- Your completed thought records
- Which patterns you noticed
- What was most challenging about this exercise
```

**Validation:**
- ✅ Structured, clear format
- ✅ Specific to client's issue (social anxiety at work)
- ✅ Includes example for clarity
- ✅ Measurable goals
- ✅ Follows CBT best practices
- ✅ Ready for practitioner to assign

---

## Summary of Haystack Features Demonstrated

| Feature | What It Does | Example # |
|---------|--------------|-----------|
| **Document Generation** | Fill templates with dynamic data | #1, #6 |
| **Persona Behavior** | Different AI personalities and response styles | #2 |
| **Tool Orchestration** | Chain multiple tools together for complex tasks | #3 |
| **Variable Substitution** | Replace {{placeholders}} with actual values | #4 |
| **Safety & Ethics** | Block harmful requests, allow legitimate ones | #5 |
| **Structured Output** | Generate formatted homework, notes, letters | #6 |

---

## How to Test These Features

### Mocked Tests (Fast, Free)
```bash
cd /Users/xukoikok/Desktop/antsa-1/haystack
python3 -m pytest tests/integration/backend/ -v
```

### Real API Tests (Slow, Costs ~$0.25)
```bash
cd /Users/xukoikok/Desktop/antsa-1/haystack
export OPENAI_API_KEY="sk-your-key-here"
python3 -m pytest -m real_ai tests/integration/backend/test_real_api_key_flows.py -v
```

---

## Cost Breakdown

Using **GPT-4o** (production model):
- **Input:** $0.0025 per 1K tokens (~$0.01 per example above)
- **Output:** $0.01 per 1K tokens (~$0.02 per example above)
- **Total per interaction:** ~$0.03 average

**Monthly estimates** (based on usage):
- 1,000 document generations: ~$30
- 10,000 chat messages: ~$300
- 50,000 tool calls: ~$1,500

---

## Next Steps

1. **Try the examples:** Copy the input data and run through Haystack API
2. **Modify parameters:** Change personas, templates, tools to see different outputs
3. **Review test coverage:** See [todo.md](todo.md) for what's tested vs. what's not
4. **Run integration tests:** Verify everything works in your environment

For questions or issues, see the main [CLAUDE.md](/CLAUDE.md) project documentation.
