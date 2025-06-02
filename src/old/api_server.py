# src/api_server.py
"""
FastAPI server for Research Agent
Orchestrates local models and provides REST API endpoints
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import asyncio
import uuid
import time
import os
from datetime import datetime

# Import our custom modules
from model_conductor import ModelConductor
from hello_agent import HelloAgent

# Initialize FastAPI app
app = FastAPI(
    title="Research Agent API",
    description="Local AI-powered research agent with multi-model orchestration",
    version="1.0.0"
)

# Add CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
model_conductor = ModelConductor()
hello_agent = HelloAgent()

# In-memory storage for jobs (will move to database later)
jobs = {}
job_results = {}

# Pydantic models for API requests/responses
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    temperature: Optional[float] = 0.7

class ChatResponse(BaseModel):
    response: str
    model_used: str
    response_time: float
    timestamp: datetime

class ResearchRequest(BaseModel):
    topic: str
    max_sources: Optional[int] = 10
    include_rag: Optional[bool] = True
    complexity: Optional[str] = "standard"  # simple, standard, complex, critical

class ResearchJob(BaseModel):
    job_id: str
    topic: str
    status: str  # pending, processing, completed, failed
    progress: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

class SystemStatus(BaseModel):
    ollama_status: str
    milvus_status: str
    loaded_models: List[Dict[str, Any]]
    system_resources: Dict[str, Any]
    version: str

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Ollama connection
        ollama_ok = hello_agent.test_connection()
        
        # Check Milvus connection (we'll implement this)
        milvus_ok = True  # TODO: Implement Milvus health check
        
        return {
            "status": "healthy" if (ollama_ok and milvus_ok) else "degraded",
            "timestamp": datetime.now(),
            "services": {
                "ollama": "online" if ollama_ok else "offline",
                "milvus": "online" if milvus_ok else "offline"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

# System status endpoint
@app.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get detailed system status"""
    try:
        # Get loaded models from Ollama
        import ollama
        client = ollama.Client()
        models_response = client.list()
        loaded_models = []
        
        # Get currently loaded models
        try:
            ps_result = client.ps()
            for model in ps_result.get('models', []):
                loaded_models.append({
                    'name': model.get('name', 'unknown'),
                    'size': model.get('size', 0),
                    'processor': model.get('processor', 'unknown'),
                    'until': model.get('until', 'unknown')
                })
        except:
            loaded_models = [{"name": "No models loaded", "size": 0}]
        
        return SystemStatus(
            ollama_status="online",
            milvus_status="online",  # TODO: Actually check Milvus
            loaded_models=loaded_models,
            system_resources={
                "active_jobs": len([j for j in jobs.values() if j["status"] == "processing"]),
                "total_jobs": len(jobs),
                "memory_usage": "TODO"  # TODO: Add actual memory monitoring
            },
            version="1.0.0"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

# Simple chat endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Simple chat endpoint for testing models"""
    try:
        start_time = time.time()
        
        # Use model conductor to select best model
        selected_model = model_conductor.select_model(
            task_type="chat",
            complexity="simple",
            preferred_model=request.model
        )
        
        # Create agent with selected model
        agent = HelloAgent(model_name=selected_model)
        
        # Generate response
        result = agent.simple_chat(request.message)
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=f"Chat failed: {result['error']}")
        
        response_time = time.time() - start_time
        
        return ChatResponse(
            response=result['response'],
            model_used=selected_model,
            response_time=response_time,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

# Research job submission
@app.post("/research", response_model=ResearchJob)
async def submit_research_job(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Submit a research job for background processing"""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job record
        job = {
            "job_id": job_id,
            "topic": request.topic,
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now(),
            "config": {
                "max_sources": request.max_sources,
                "include_rag": request.include_rag,
                "complexity": request.complexity
            }
        }
        
        jobs[job_id] = job
        
        # Start background research task
        background_tasks.add_task(process_research_job, job_id, request)
        
        return ResearchJob(
            job_id=job_id,
            topic=request.topic,
            status="pending",
            progress=0,
            created_at=job["created_at"],
            estimated_completion=None  # TODO: Estimate based on complexity
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research submission failed: {str(e)}")

# Get research job status
@app.get("/research/{job_id}")
async def get_research_job(job_id: str):
    """Get research job status and results"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "topic": job["topic"],
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at")
    }
    
    # Include results if completed
    if job["status"] == "completed" and job_id in job_results:
        response["results"] = job_results[job_id]
    
    return response

# List all research jobs
@app.get("/research")
async def list_research_jobs():
    """List all research jobs"""
    return [
        {
            "job_id": job_id,
            "topic": job["topic"],
            "status": job["status"],
            "progress": job["progress"],
            "created_at": job["created_at"]
        }
        for job_id, job in jobs.items()
    ]

# Model management endpoints
@app.get("/models")
async def list_models():
   """List available and loaded models"""
    try:
        import ollama
        client = ollama.Client()
        
        # Get all available models
        available = client.list()
        
        # Get currently loaded models
        try:
            loaded = client.ps()
            loaded_models = loaded.get('models', [])
        except:
            loaded_models = []
        
        return {
            "available_models": [
                {
                    "name": model.get("name", "unknown"),
                    "size": model.get("size", 0),
                    "modified": model.get("modified_at", model.get("modified", "unknown"))
                }
                for model in available.get("models", [])
            ],
            "loaded_models": loaded_models
        }
    except Exception as e:
        return {
            "error": f"Model listing failed: {str(e)}",
            "available_models": [],
            "loaded_models": []
        }

@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    """Load a specific model into memory"""
    try:
        # Use model conductor to check if we can load this model
        can_load = model_conductor.can_load_model(model_name)
        
        if not can_load:
            raise HTTPException(status_code=400, detail="Cannot load model - insufficient resources")
        
        # Load the model by making a simple request
        agent = HelloAgent(model_name=model_name)
        result = agent.simple_chat("Hello")
        
        if result['success']:
            return {"message": f"Model {model_name} loaded successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to load model: {result['error']}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model loading failed: {str(e)}")

# Background task for processing research jobs
async def process_research_job(job_id: str, request: ResearchRequest):
    """Background task to process research jobs"""
    try:
        # Update job status
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 10
        
        # Simulate research process (we'll implement real research later)
        await asyncio.sleep(2)  # Simulate web research
        jobs[job_id]["progress"] = 30
        
        await asyncio.sleep(2)  # Simulate document analysis
        jobs[job_id]["progress"] = 60
        
        await asyncio.sleep(2)  # Simulate report generation
        jobs[job_id]["progress"] = 90
        
        # Generate mock research result
        selected_model = model_conductor.select_model(
            task_type="research",
            complexity=request.complexity
        )
        
        agent = HelloAgent(model_name=selected_model)
        research_prompt = f"""
        Conduct research on the topic: {request.topic}
        
        Please provide:
        1. Executive Summary
        2. Key Findings
        3. Important Sources (mock for now)
        4. Recommendations
        
        Keep it concise but informative.
        """
        
        result = agent.simple_chat(research_prompt)
        
        if result['success']:
            # Store results
            job_results[job_id] = {
                "report": result['response'],
                "model_used": selected_model,
                "sources": ["https://example.com/source1", "https://example.com/source2"],  # Mock sources
                "processing_time": result['response_time'],
                "timestamp": datetime.now()
            }
            
            # Mark job as completed
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["completed_at"] = datetime.now()
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = result['error']
            
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

# Development endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Research Agent API",
        "version": "1.0.0",
        "description": "Local AI-powered research agent",
        "endpoints": {
            "health": "/health",
            "status": "/status", 
            "chat": "/chat",
            "research": "/research",
            "models": "/models"
        },
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Research Agent API Server...")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("🔍 Health Check: http://localhost:8000/health")
    
    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=8001, 
        reload=True,
        log_level="info"
    )
