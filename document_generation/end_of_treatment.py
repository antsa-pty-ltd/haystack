"""
End-of-treatment document generation
Generates comprehensive treatment summary letters after completing therapy
"""
import logging
from typing import Dict, Any, List
from datetime import datetime
from openai import OpenAI
import os

from pii_utils import is_tokenized, sanitize_for_logging, sanitize_dict_for_logging

logger = logging.getLogger(__name__)

class EndOfTreatmentGenerator:
    """Generates end-of-treatment summary letters from multiple therapy sessions"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_letter(
        self,
        client_info: Dict[str, Any],
        practitioner_info: Dict[str, Any],
        sessions: List[Dict[str, Any]],
        treatment_goals: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive end-of-treatment letter
        
        Args:
            client_info: Client details (name, age, presenting issues)
            practitioner_info: Practitioner details (name, title, registration)
            sessions: List of session summaries with transcripts
            treatment_goals: Initial treatment goals if available
            
        Returns:
            Dictionary containing the generated letter and metadata
        """
        try:
            logger.info(f"🏁 Generating end-of-treatment letter for {len(sessions)} sessions")
            
            # Build comprehensive prompt with all session data
            prompt = self._build_letter_prompt(
                client_info,
                practitioner_info,
                sessions,
                treatment_goals
            )
            
            # Generate letter using GPT-4
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an experienced clinical psychologist writing a professional end-of-treatment summary letter.

Your letter should be:
- Professional and clinical in tone
- Evidence-based, citing specific progress from sessions
- Non-diagnostic (describe symptoms, not diagnoses)
- Focused on outcomes and recommendations
- Suitable for referring doctors or healthcare professionals

Format the letter as a formal medical document."""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=3000,
            )
            
            letter_content = response.choices[0].message.content
            
            logger.info(f"✅ End-of-treatment letter generated ({len(letter_content)} characters)")
            
            return {
                "letter": letter_content,
                "metadata": {
                    "client_name": client_info.get('name', '[CLIENT_NAME]'),
                    "practitioner_name": practitioner_info.get('name', '[PRACTITIONER_NAME]'),
                    "session_count": len(sessions),
                    "treatment_period": self._get_treatment_period(sessions),
                    "generated_at": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to generate end-of-treatment letter: {e}")
            raise
    
    def _build_letter_prompt(
        self,
        client_info: Dict[str, Any],
        practitioner_info: Dict[str, Any],
        sessions: List[Dict[str, Any]],
        treatment_goals: List[str] = None
    ) -> str:
        """Build the prompt for GPT-4 letter generation"""
        
        # Extract client identifier.
        # PRIVACY: The NestJS api sends a tokenized identifier (e.g. [CLIENT_NAME])
        # in client_info['name']; the real name is substituted back only AFTER the
        # LLM call. Use that token — do NOT concatenate firstName/lastName, which
        # would leak real PII into the OpenAI prompt.
        client_name = client_info.get('name', '[CLIENT_NAME]')
        client_age = client_info.get('age', 'N/A')
        client_gender = client_info.get('gender', 'N/A')

        # Extract practitioner identifier (tokenized — see note above).
        practitioner_name = practitioner_info.get('name', '[PRACTITIONER_NAME]')
        practitioner_title = practitioner_info.get('title', 'Clinical Psychologist')

        # Defensive guard: if a real (untokenized) name slipped through from the
        # caller, do NOT send it to OpenAI. Log a sanitized warning and degrade
        # safely to the placeholder token. Never crash document generation.
        if not is_tokenized(client_name):
            logger.warning(
                "⚠️ Untokenized client name reached end-of-treatment prompt builder; "
                "replacing with [CLIENT_NAME]. client_info=%s",
                sanitize_dict_for_logging(client_info),
            )
            client_name = "[CLIENT_NAME]"
        if not is_tokenized(practitioner_name):
            logger.warning(
                "⚠️ Untokenized practitioner name reached end-of-treatment prompt builder; "
                "replacing with [PRACTITIONER_NAME]. practitioner_info=%s",
                sanitize_dict_for_logging(practitioner_info),
            )
            practitioner_name = "[PRACTITIONER_NAME]"
        
        # Get treatment period
        treatment_period = self._get_treatment_period(sessions)
        
        # Summarize sessions
        session_summaries = self._summarize_sessions(sessions)
        
        # Build goals section
        goals_section = ""
        if treatment_goals:
            goals_section = f"""
INITIAL TREATMENT GOALS:
{chr(10).join([f"- {goal}" for goal in treatment_goals])}
"""
        
        return f"""Generate a comprehensive end-of-treatment summary letter with the following information:

CLIENT INFORMATION:
- Name: {client_name}
- Age: {client_age}
- Gender: {client_gender}

PRACTITIONER INFORMATION:
- Name: {practitioner_name}
- Title: {practitioner_title}

TREATMENT PERIOD:
- First Session: {treatment_period['start']}
- Last Session: {treatment_period['end']}
- Total Sessions: {len(sessions)}

{goals_section}

SESSION SUMMARIES:
{session_summaries}

Please generate a professional end-of-treatment letter that includes:

1. **Treatment Summary**: Overview of the treatment period and number of sessions
2. **Initial Presentation**: Client's presenting concerns at the start of treatment
3. **Treatment Approach**: Therapeutic modalities used (CBT, ACT, mindfulness, etc.)
4. **Progress and Outcomes**: 
   - Specific improvements observed across sessions
   - Skills developed and strategies learned
   - Behavioral and emotional changes
5. **Goals Achieved**: Assessment of progress toward initial goals
6. **Recommendations for Ongoing Care**: 
   - Maintenance strategies
   - Potential need for future support
   - Self-care practices to continue
7. **Discharge Summary**: Final clinical impression and date of discharge

Format the letter as a formal clinical document addressed to "To Whom It May Concern" or the referring physician."""

    def _summarize_sessions(self, sessions: List[Dict[str, Any]]) -> str:
        """Create a concise summary of all sessions for the prompt"""
        summaries = []
        
        for i, session in enumerate(sessions, 1):
            date = session.get('scheduledStartTime', 'Unknown date')
            summary = session.get('summary', '')
            key_themes = session.get('themes', [])
            
            session_summary = f"""
Session {i} ({date}):
Key Themes: {', '.join(key_themes) if key_themes else 'N/A'}
Summary: {summary[:500] if summary else 'No summary available'}
"""
            summaries.append(session_summary)
        
        return "\n".join(summaries)
    
    def _get_treatment_period(self, sessions: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract start and end dates from sessions"""
        if not sessions:
            return {"start": "N/A", "end": "N/A"}
        
        dates = [s.get('scheduledStartTime') for s in sessions if s.get('scheduledStartTime')]
        
        if not dates:
            return {"start": "N/A", "end": "N/A"}
        
        sorted_dates = sorted(dates)
        
        return {
            "start": sorted_dates[0],
            "end": sorted_dates[-1]
        }

# Global instance
end_of_treatment_generator = EndOfTreatmentGenerator()
