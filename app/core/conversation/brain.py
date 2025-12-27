# app/core/conversation/brain.py
"""
Conversation Brain - Central Decision Engine (COMMANDER)

RESPONSIBILITY:
- Entry point for all chat interactions
- Receives: user_id, user_message
- Determines current conversation stage
- Requests text from prompts.py
- Updates memory via memory.py
- Returns assistant message + metadata
- NO database queries directly
- NO hardcoded text
"""

from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.core.conversation.stages import ConversationStage, get_stage, transition_stage
from app.core.conversation.memory import ConversationMemory
from app.core.conversation.context import ConversationContext
from app.core.conversation.prompts import ConversationPrompts
from app.models import User


class ConversationBrain:
    """Central decision engine for all conversation interactions"""
    
    def __init__(self, db: Session, language: str = "en"):
        self.db = db
        self.language = language
        self.memory = ConversationMemory(db)
        self.prompts = ConversationPrompts(language)
    
    def process_message(
        self,
        user_id: int,
        user_message: str
    ) -> Dict[str, any]:
        """
        Process user message and generate Sedi's response.
        
        Flow:
        1. Get current conversation stage
        2. Build conversation context
        3. Generate response using prompts
        4. Save conversation to memory
        5. Check for stage transition
        6. Return response with metadata
        
        Args:
            user_id: User ID
            user_message: User's message
        
        Returns:
            Dict with:
            - message: Sedi's response text
            - language: Language code
            - stage: Current conversation stage
            - metadata: Optional metadata (tone, intent, etc.)
        """
        # TEMP DEBUG: Log entry
        print(f"[BRAIN DEBUG] ===== PROCESSING MESSAGE =====")
        print(f"[BRAIN DEBUG] user_id={user_id}, message={user_message[:50]}...")
        
        # Validate user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"[BRAIN DEBUG] ERROR: User not found")
            return {
                "message": self._get_error_message("user_not_found"),
                "language": self.language,
                "stage": None,
                "error": "User not found"
            }
        
        # Get current stage
        current_stage = get_stage(user_id, self.db)
        print(f"[BRAIN DEBUG] Current stage: {current_stage.value}")
        
        # Build context
        context = ConversationContext(
            user_id=user_id,
            stage=current_stage,
            memory=self.memory,
            user_message=user_message
        )
        context_data = context.build()
        print(f"[BRAIN DEBUG] Context built - conversation_count={context_data.get('conversation_count', 0)}")
        
        # Determine engagement level (minimal logic - selection only)
        engagement_level = self._determine_engagement_level(context_data)
        print(f"[BRAIN DEBUG] Engagement level: {engagement_level}")
        
        # Generate response with engagement-aware prompts
        sedi_response = self.prompts.generate_response(
            context_data, 
            user_message,
            engagement_level
        )
        print(f"[BRAIN DEBUG] Response generated (length={len(sedi_response)})")
        
        # Save conversation to memory
        self.memory.save_conversation(
            user_id=user_id,
            user_message=user_message,
            sedi_response=sedi_response,
            language=self.language
        )
        
        # Check for stage transition
        new_stage = transition_stage(current_stage, user_id, self.db)
        print(f"[BRAIN DEBUG] New stage: {new_stage.value}")
        print(f"[BRAIN DEBUG] ===== MESSAGE PROCESSED =====")
        
        # Build metadata
        metadata = {
            "stage": new_stage.value,
            "conversation_count": context_data.get("conversation_count", 0) + 1,
            "tone": self._infer_tone(sedi_response),
        }
        
        return {
            "message": sedi_response,
            "language": self.language,
            "stage": new_stage.value,
            "metadata": metadata
        }
    
    def get_greeting(self, user_id: int) -> Dict[str, any]:
        """
        Generate initial greeting for user.
        
        Used when user first opens chat or returns after absence.
        
        Args:
            user_id: User ID
        
        Returns:
            Dict with greeting message and metadata
        """
        # Get current stage
        stage = get_stage(user_id, self.db)
        
        # Build context
        context = ConversationContext(
            user_id=user_id,
            stage=stage,
            memory=self.memory
        )
        context_data = context.build()
        
        # Generate greeting based on stage
        greeting = self._generate_greeting(context_data, stage)
        
        return {
            "message": greeting,
            "language": self.language,
            "stage": stage.value,
            "metadata": {
                "type": "greeting",
                "stage": stage.value
            }
        }
    
    def _generate_greeting(
        self,
        context: Dict[str, any],
        stage: ConversationStage
    ) -> str:
        """
        Generate greeting message based on context and stage.
        
        SCENARIO 7: Daily greeting - calm, optional, no reply required.
        """
        user_name = context.get("user_name") or "friend"
        time_since = context.get("time_since_last")
        engagement_level = self._determine_engagement_level(context)
        
        # Build greeting prompt - calm and non-intrusive
        if stage == ConversationStage.FIRST_CONTACT:
            greeting_prompt = f"Say hello and introduce yourself as Sedi. Use their name: {user_name}. Keep it brief and calm."
        elif time_since:
            # User returning after absence - be warm but not pushy
            greeting_prompt = f"Greet {user_name} calmly. You haven't talked in a while. Be warm but not overwhelming. No pressure to respond."
        else:
            # Regular greeting - short and optional
            greeting_prompt = f"Greet {user_name} with a calm, short greeting. This is optional - no reply required. Keep it brief."
        
        try:
            completion = self.prompts._build_system_prompt(
                stage,
                user_name,
                context.get("conversation_count", 0),
                engagement_level
            )
            
            # Add greeting-specific instruction
            greeting_instruction = {
                "en": "\nThis is a greeting message. Keep it calm and brief. No questions required. User can respond if they want, or not.",
                "fa": "\nاین یک پیام سلام است. آرام و مختصر نگه دار. سوال لازم نیست. کاربر می‌تواند پاسخ دهد یا نه.",
                "ar": "\nهذه رسالة تحية. اجعلها هادئة ومختصرة. لا أسئلة مطلوبة. يمكن للمستخدم الرد إذا أراد، أو لا."
            }
            
            completion += greeting_instruction.get(self.language, greeting_instruction["en"])
            
            messages = [
                {"role": "system", "content": completion},
                {"role": "user", "content": greeting_prompt}
            ]
            
            from app.core.conversation.prompts import client as gpt_client
            response = gpt_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=80,  # Shorter for greetings
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"[BRAIN GREETING ERROR] {e}")
            return self.prompts._get_fallback_response(stage)
    
    def _determine_engagement_level(self, context: Dict[str, any]) -> str:
        """
        Determine user engagement level based on conversation patterns.
        
        MINIMAL logic - selection only, no complex calculations.
        
        Returns:
            "low": User rarely responds, long gaps
            "normal": Standard engagement
            "high": User is very engaged, frequent responses
        """
        conversation_count = context.get("conversation_count", 0)
        time_since_last = context.get("time_since_last")
        recent_messages = context.get("recent_messages", [])
        
        # Low engagement indicators
        if conversation_count > 0:
            if time_since_last:
                # Parse time delta (format: "X days, Y:Z:W")
                try:
                    days = 0
                    if "day" in time_since_last.lower():
                        days = int(time_since_last.split()[0])
                    if days > 7:  # More than a week
                        return "low"
                except:
                    pass
            
            # Check recent message frequency
            if len(recent_messages) < 2 and conversation_count > 5:
                return "low"
        
        # High engagement indicators
        if len(recent_messages) >= 3 and conversation_count > 3:
            # User has been actively chatting
            return "high"
        
        # Default to normal
        return "normal"
    
    def _infer_tone(self, message: str) -> str:
        """Infer tone from message (simple heuristic)"""
        message_lower = message.lower()
        if any(word in message_lower for word in ["!", "urgent", "important"]):
            return "urgent"
        elif any(word in message_lower for word in ["?", "wonder", "curious"]):
            return "curious"
        elif any(word in message_lower for word in ["😊", "happy", "glad", "great"]):
            return "warm"
        else:
            return "neutral"
    
    def _get_error_message(self, error_type: str) -> str:
        """Get error message based on type"""
        error_messages = {
            "user_not_found": {
                "en": "I'm sorry, I couldn't find your account. Please try again.",
                "fa": "متاسفم، نتوانستم حساب کاربری شما را پیدا کنم. لطفاً دوباره تلاش کنید.",
                "ar": "عذراً، لم أتمكن من العثور على حسابك. يرجى المحاولة مرة أخرى."
            }
        }
        
        return error_messages.get(error_type, {}).get(
            self.language,
            error_messages.get(error_type, {}).get("en", "An error occurred.")
        )

