from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import openai
import requests
import json
import os
from datetime import datetime, timedelta
import logging
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from twilio.rest import Client as TwilioClient
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Virtual C-Suite Boardroom API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# Initialize OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Initialize Twilio
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Data Models
class ExecutiveResponse(BaseModel):
    message: str
    executives: List[str]

class SlackMessage(BaseModel):
    message: str
    channel: Optional[str] = "#executive-insights"

class NotionPage(BaseModel):
    title: str
    content: str

class GoogleQuery(BaseModel):
    query: str
    service: str = "search"

class TwilioCall(BaseModel):
    to_number: str
    message: str

# In-memory storage (replace with database in production)
chat_history = []
analytics_data = {
    "total_conversations": 0,
    "executive_usage": {},
    "daily_stats": {},
    "response_times": []
}

# AI Executive Personalities
EXECUTIVES = {
    # Executive Department
    "garrett": {
        "name": "Garrett",
        "title": "Chief Executive Officer (CEO)",
        "department": "Executive",
        "personality": "Visionary leader focused on strategic direction, market positioning, and long-term growth. Thinks big picture and makes decisive calls.",
        "expertise": ["Strategic Vision", "Leadership", "Market Positioning", "Stakeholder Relations", "Corporate Strategy"]
    },
    "melon": {
        "name": "Melon",
        "title": "Chief Operating Officer (COO)",
        "department": "Executive",
        "personality": "Operations-focused executive who optimizes processes, improves efficiency, and ensures smooth day-to-day operations.",
        "expertise": ["Operations Management", "Process Optimization", "Efficiency", "Team Coordination", "Operational Strategy"]
    },
    "steve": {
        "name": "Steve",
        "title": "Chief Technology Officer (CTO)",
        "department": "Executive",
        "personality": "Technology strategist who drives innovation, scalable solutions, and digital transformation initiatives.",
        "expertise": ["Technology Strategy", "Innovation", "Scalable Architecture", "Digital Transformation", "Tech Leadership"]
    },
    "grant": {
        "name": "Grant",
        "title": "Chief Strategy Officer (CSO)",
        "department": "Executive",
        "personality": "Strategic analyst who provides competitive intelligence, market analysis, and strategic planning insights.",
        "expertise": ["Strategic Analysis", "Competitive Intelligence", "Market Research", "Business Planning", "Growth Strategy"]
    },
    
    # Finance Department
    "xander": {
        "name": "Xander",
        "title": "Chief Financial Officer (CFO)",
        "department": "Finance",
        "personality": "Financial strategist focused on ROI analysis, risk management, and sustainable financial growth.",
        "expertise": ["Financial Strategy", "ROI Analysis", "Risk Management", "Financial Planning", "Investment Strategy"]
    },
    "sarah": {
        "name": "Sarah",
        "title": "Bookkeeper",
        "department": "Finance",
        "personality": "Detail-oriented financial professional ensuring accuracy in accounting, compliance, and financial records.",
        "expertise": ["Accounting", "Compliance", "Financial Records", "Bookkeeping", "Financial Controls"]
    },
    "don": {
        "name": "Don",
        "title": "Investment Manager",
        "department": "Finance",
        "personality": "Portfolio management expert focused on investment strategy and maximizing returns while managing risk.",
        "expertise": ["Portfolio Management", "Investment Strategy", "Asset Allocation", "Risk Assessment", "Market Analysis"]
    },
    
    # Marketing Department
    "aleks": {
        "name": "Aleks",
        "title": "Chief Marketing Officer (CMO)",
        "department": "Marketing",
        "personality": "Marketing strategist who drives brand management, customer engagement, and market positioning.",
        "expertise": ["Marketing Strategy", "Brand Management", "Customer Engagement", "Market Positioning", "Growth Marketing"]
    },
    "ashley": {
        "name": "Ashley",
        "title": "Creative Director",
        "department": "Marketing",
        "personality": "Creative visionary who develops visual identity, creative concepts, and brand aesthetics.",
        "expertise": ["Visual Identity", "Creative Concepts", "Brand Aesthetics", "Design Strategy", "Creative Leadership"]
    },
    "gray": {
        "name": "Gray",
        "title": "Brand Strategist",
        "department": "Marketing",
        "personality": "Brand positioning expert who conducts market research and develops brand strategy.",
        "expertise": ["Brand Positioning", "Market Research", "Brand Strategy", "Consumer Insights", "Brand Development"]
    },
    "yu": {
        "name": "Yu",
        "title": "Ad Strategist",
        "department": "Marketing",
        "personality": "Performance marketing specialist focused on campaign optimization and measurable results.",
        "expertise": ["Performance Marketing", "Campaign Optimization", "Digital Advertising", "Analytics", "Conversion Optimization"]
    },
    "jimmy": {
        "name": "Jimmy",
        "title": "Content Strategist",
        "department": "Marketing",
        "personality": "Content marketing expert who develops storytelling strategies and content frameworks.",
        "expertise": ["Content Marketing", "Storytelling", "Content Strategy", "Editorial Planning", "Content Distribution"]
    },
    "alejandra": {
        "name": "Alejandra",
        "title": "Graphic Designer",
        "department": "Marketing",
        "personality": "Visual design specialist who creates brand assets and maintains visual consistency.",
        "expertise": ["Visual Design", "Brand Assets", "Graphic Design", "Visual Communication", "Design Systems"]
    },
    
    # Human Resources
    "kimberly": {
        "name": "Kimberly",
        "title": "HR Director",
        "department": "Human Resources",
        "personality": "People management expert focused on organizational development and team dynamics.",
        "expertise": ["People Management", "Organizational Development", "Team Dynamics", "HR Strategy", "Talent Management"]
    },
    "lauren": {
        "name": "Lauren",
        "title": "Numerologist",
        "department": "Human Resources",
        "personality": "Analytics specialist who provides data insights, forecasting, and performance metrics.",
        "expertise": ["Analytics", "Data Insights", "Forecasting", "Performance Metrics", "Statistical Analysis"]
    },
    
    # Real Estate Department
    "garyn": {
        "name": "Garyn",
        "title": "Chief Real Estate Officer (CREO)",
        "department": "Real Estate",
        "personality": "Real estate strategist focused on property management and real estate investment strategy.",
        "expertise": ["Real Estate Strategy", "Property Management", "Real Estate Investment", "Market Analysis", "Portfolio Optimization"]
    },
    "jace": {
        "name": "Jace",
        "title": "Creative Finance Director",
        "department": "Real Estate",
        "personality": "Real estate financing expert who develops creative investment structures and financing solutions.",
        "expertise": ["Real Estate Financing", "Investment Structures", "Creative Financing", "Capital Strategy", "Deal Structuring"]
    },
    "wise": {
        "name": "Wise",
        "title": "Acquisitions Director",
        "department": "Real Estate",
        "personality": "Property acquisition specialist focused on market analysis and investment opportunities.",
        "expertise": ["Property Acquisition", "Market Analysis", "Investment Opportunities", "Due Diligence", "Deal Evaluation"]
    }
}

# Helper Functions
def track_analytics(executive_list: List[str], response_time: float):
    """Track analytics data"""
    analytics_data["total_conversations"] += 1
    
    for exec_id in executive_list:
        if exec_id in analytics_data["executive_usage"]:
            analytics_data["executive_usage"][exec_id] += 1
        else:
            analytics_data["executive_usage"][exec_id] = 1
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today in analytics_data["daily_stats"]:
        analytics_data["daily_stats"][today] += 1
    else:
        analytics_data["daily_stats"][today] = 1
    
    analytics_data["response_times"].append(response_time)

def send_slack_notification(message: str, executives: List[str]):
    """Send automatic Slack notification"""
    try:
        if not SLACK_WEBHOOK_URL:
            return False
            
        exec_names = [EXECUTIVES[exec_id]["name"] for exec_id in executives if exec_id in EXECUTIVES]
        slack_payload = {
            "text": f"🏢 Executive Boardroom Discussion",
            "attachments": [
                {
                    "color": "good",
                    "fields": [
                        {
                            "title": "Executives Consulted",
                            "value": ", ".join(exec_names),
                            "short": True
                        },
                        {
                            "title": "Discussion Topic",
                            "value": message[:200] + "..." if len(message) > 200 else message,
                            "short": False
                        }
                    ],
                    "footer": "Virtual C-Suite Boardroom",
                    "ts": int(datetime.now().timestamp())
                }
            ]
        }
        
        response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return False

async def get_executive_response(executive_id: str, message: str, context: str = "") -> str:
    """Get response from a specific executive"""
    try:
        if executive_id not in EXECUTIVES:
            return f"Executive {executive_id} not found."
        
        executive = EXECUTIVES[executive_id]
        
        system_prompt = f"""You are {executive['name']}, {executive['title']} at a company. 
        
Your personality: {executive['personality']}
Your expertise: {', '.join(executive['expertise'])}
Department: {executive['department']}

Respond as this executive would, drawing on your specific expertise and personality. 
Keep responses focused, actionable, and in character. Aim for 2-3 paragraphs maximum.
"""

        if context:
            system_prompt += f"\n\nConversation context: {context}"

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        logger.error(f"OpenAI API error for {executive_id}: {e}")
        return f"I apologize, but I'm currently unable to provide a response. Please try again shortly."

# API Endpoints

@app.get("/")
async def root():
    return {"message": "Virtual C-Suite Boardroom API", "status": "active", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": bool(OPENAI_API_KEY),
            "slack": bool(SLACK_WEBHOOK_URL),
            "notion": bool(NOTION_API_KEY),
            "google": bool(GOOGLE_API_KEY),
            "twilio": bool(twilio_client)
        },
        "executives_loaded": len(EXECUTIVES),
        "total_conversations": analytics_data["total_conversations"]
    }
    return health_status

@app.get("/api/executives")
async def get_executives():
    """Get all executive profiles"""
    return {"executives": EXECUTIVES}

@app.post("/api/executive-response")
async def get_executive_responses(request: ExecutiveResponse):
    """Get responses from selected executives"""
    start_time = datetime.now()
    
    try:
        # Get conversation context (last 3 messages)
        context = ""
        if len(chat_history) > 0:
            recent_messages = chat_history[-3:]
            context = " | ".join([f"{msg.get('user', 'User')}: {msg.get('message', '')}" for msg in recent_messages])
        
        # Get responses from each selected executive
        responses = {}
        tasks = []
        
        for executive_id in request.executives:
            if executive_id in EXECUTIVES:
                task = get_executive_response(executive_id, request.message, context)
                tasks.append((executive_id, task))
        
        # Execute all requests concurrently
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        # Process results
        for i, (executive_id, _) in enumerate(tasks):
            if isinstance(results[i], Exception):
                responses[executive_id] = f"I apologize, but I'm currently unavailable. Please try again."
            else:
                responses[executive_id] = results[i]
        
        # Store in chat history
        chat_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": request.message,
            "executives": request.executives,
            "responses": responses
        }
        chat_history.append(chat_entry)
        
        # Track analytics
        response_time = (datetime.now() - start_time).total_seconds()
        track_analytics(request.executives, response_time)
        
        # Send Slack notification (async, don't wait)
        asyncio.create_task(asyncio.to_thread(send_slack_notification, request.message, request.executives))
        
        return {
            "responses": responses,
            "timestamp": chat_entry["timestamp"],
            "executives_consulted": len(responses)
        }
        
    except Exception as e:
        logger.error(f"Error in executive responses: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/chat-history")
async def get_chat_history(limit: int = 10):
    """Get recent chat history"""
    return {"history": chat_history[-limit:]}

@app.get("/api/analytics")
async def get_analytics():
    """Get usage analytics"""
    avg_response_time = sum(analytics_data["response_times"]) / len(analytics_data["response_times"]) if analytics_data["response_times"] else 0
    
    return {
        "total_conversations": analytics_data["total_conversations"],
        "executive_usage": analytics_data["executive_usage"],
        "daily_stats": analytics_data["daily_stats"],
        "average_response_time": round(avg_response_time, 2),
        "most_popular_executive": max(analytics_data["executive_usage"].items(), key=lambda x: x[1])[0] if analytics_data["executive_usage"] else None
    }

# Slack Integration
@app.post("/api/slack/send")
async def send_slack_message(message: SlackMessage):
    """Send message to Slack"""
    try:
        if not SLACK_WEBHOOK_URL:
            raise HTTPException(status_code=400, detail="Slack webhook not configured")
        
        payload = {
            "text": message.message,
            "channel": message.channel
        }
        
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            return {"success": True, "message": "Message sent to Slack"}
        else:
            raise HTTPException(status_code=response.status_code, detail="Slack API error")
    
    except Exception as e:
        logger.error(f"Slack send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/slack/test")
async def test_slack():
    """Test Slack integration"""
    try:
        test_message = SlackMessage(message="🧪 Virtual C-Suite Boardroom - Connection Test Successful!")
        result = await send_slack_message(test_message)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}

# Notion Integration
@app.post("/api/notion/test")
async def test_notion():
    """Test Notion integration"""
    try:
        if not NOTION_API_KEY:
            return {"success": False, "error": "Notion API key not configured"}
        
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        response = requests.get("https://api.notion.com/v1/users/me", headers=headers, timeout=10)
        
        if response.status_code == 200:
            return {"success": True, "message": "Notion connection successful"}
        else:
            return {"success": False, "error": f"Notion API error: {response.status_code}"}
    
    except Exception as e:
        logger.error(f"Notion test error: {e}")
        return {"success": False, "error": str(e)}

# Google Integration  
@app.post("/api/google/test")
async def test_google():
    """Test Google integration"""
    try:
        if not GOOGLE_API_KEY:
            return {"success": False, "error": "Google API key not configured"}
        
        return {"success": True, "message": "Google API key configured"}
    
    except Exception as e:
        logger.error(f"Google test error: {e}")
        return {"success": False, "error": str(e)}

# Twilio Integration
@app.post("/api/twilio/test")
async def test_twilio():
    """Test Twilio integration"""
    try:
        if not twilio_client:
            return {"success": False, "error": "Twilio not configured"}
        
        account = twilio_client.api.accounts.get()
        return {"success": True, "message": f"Twilio connected: {account.sid}"}
    
    except Exception as e:
        logger.error(f"Twilio test error: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
