# src/api_server.py - Version 5
"""
FastAPI server for Research Agent
Orchestrates local models and provides REST API endpoints
Fixed version with proper Ollama PS handling
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import asyncio
import uuid
import time
import os
import subprocess
from datetime import datetime

# Import our custom modules
from model_conductor import ModelConductor
from hello_agent import HelloAgent

def get_loaded_models():
    """Get currently loaded models using ollama ps command"""
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            models = []
            
            # Skip header line
            for line in lines[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        models.append({
                            'name': parts[0],
                            'id': parts[1],
                            'size': parts[2] + ' ' + parts[3],
                            'processor': parts[4] if len(parts) > 4 else 'unknown',
                            'until': ' '.join(parts[5:]) if len(parts) > 5 else 'unknown'
                        })
            
            return {'models': models}
        else:
            return {'models': []}
    except Exception as e:
        return {'models': [{'error': f'Failed to get loaded models: {str(e)}'}]}

# Initialize FastAPI app
app = FastAPI(
    title="Research Agent API",
    description="Local AI-powered research agent with multi-model orchestration",
    version="5.0.0"
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
    
    model_config = {"protected_namespaces": ()}  # Fixed Pydantic warning

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

class TaskRecommendationRequest(BaseModel):
    task_description: str

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Ollama connection
        ollama_ok = hello_agent.test_connection()
        
        # Check Milvus connection (simplified for now)
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
        # Get loaded models using our fixed function
        loaded_models = get_loaded_models().get('models', [])
        
        return SystemStatus(
            ollama_status="online",
            milvus_status="online",  # TODO: Actually check Milvus
            loaded_models=loaded_models,
            system_resources={
                "active_jobs": len([j for j in jobs.values() if j["status"] == "processing"]),
                "total_jobs": len(jobs),
                "memory_usage": "TODO"  # TODO: Add actual memory monitoring
            },
            version="5.0.0"
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

# Model management endpoints - FIXED VERSION
@app.get("/models")
async def list_models():
    """List available and loaded models"""
    try:
        import ollama
        client = ollama.Client()
        
        # Get all available models with robust error handling
        available_models = []
        try:
            available = client.list()
            
            for model in available.get("models", []):
                # Safely extract fields
                model_info = {
                    "name": model.get("name", "unknown"),
                    "size": model.get("size", 0)
                }
                
                # Try different field names for modification time
                for time_field in ["modified_at", "modified", "updated_at", "created_at"]:
                    if time_field in model:
                        model_info["modified"] = str(model[time_field])
                        break
                else:
                    model_info["modified"] = "unknown"
                    
                available_models.append(model_info)
                
        except Exception as e:
            available_models = [{"error": f"Failed to get available models: {str(e)}"}]
        
        # Get currently loaded models using our fixed function
        loaded_models_result = get_loaded_models()
        loaded_models = loaded_models_result.get('models', [])
        
        # Get model conductor analytics
        analytics = {}
        try:
            analytics = model_conductor.get_usage_analytics()
        except Exception as e:
            analytics = {"error": f"Analytics failed: {str(e)}"}
        
        return {
            "available_models": available_models,
            "loaded_models": loaded_models,
            "model_conductor_analytics": analytics,
            "total_available": len(available_models),
            "total_loaded": len([m for m in loaded_models if 'error' not in m])
        }
        
    except Exception as e:
        return {
            "error": f"Model listing failed: {str(e)}",
            "available_models": [],
            "loaded_models": [],
            "model_conductor_analytics": {},
            "debug_info": {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        }

@app.post("/models/{model_name}/load")
async def load_model(model_name: str):
    """Load a specific model into memory"""
    try:
        # Use model conductor to check if we can load this model
        can_load = model_conductor.can_load_model(model_name)
        
        if not can_load:
            return {
                "success": False,
                "message": f"Cannot load model {model_name} - insufficient resources",
                "current_memory_usage": f"{model_conductor.estimate_memory_usage():.1f}GB",
                "max_memory": f"{model_conductor.max_memory_gb}GB"
            }
        
        # Load the model by making a simple request
        agent = HelloAgent(model_name=model_name)
        result = agent.simple_chat("Hello")
        
        if result['success']:
            return {
                "success": True,
                "message": f"Model {model_name} loaded successfully",
                "response_time": result['response_time'],
                "memory_usage": f"{model_conductor.estimate_memory_usage():.1f}GB"
            }
        else:
            return {
                "success": False,
                "message": f"Failed to load model: {result['error']}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "message": f"Model loading failed: {str(e)}",
            "error_type": type(e).__name__
        }

# Model recommendations endpoint
@app.post("/models/recommend")
async def get_model_recommendations(request: TaskRecommendationRequest):
    """Get model recommendations for a task"""
    try:
        recommendations = model_conductor.get_model_recommendations(request.task_description)
        return {
            "success": True,
            "task_description": request.task_description,
            "recommendations": recommendations
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Recommendation failed: {str(e)}",
            "task_description": request.task_description
        }

# Analytics endpoint
@app.get("/analytics")
async def get_analytics():
    """Get usage analytics and system performance"""
    try:
        analytics = model_conductor.get_usage_analytics()
        
        # Get current loaded models using our fixed function
        loaded_models_result = get_loaded_models()
        current_models = [model.get('name', 'unknown') for model in loaded_models_result.get('models', []) if 'error' not in model]
        
        analytics.update({
            "system_info": {
                "currently_loaded_models": current_models,
                "total_jobs_processed": len(jobs),
                "active_jobs": len([j for j in jobs.values() if j["status"] == "processing"]),
                "api_version": "5.0.0"
            }
        })
        
        return analytics
        
    except Exception as e:
        return {
            "error": f"Analytics failed: {str(e)}",
            "error_type": type(e).__name__,
            "message": "Analytics service temporarily unavailable"
        }

# Debug endpoint
@app.get("/debug/routes")
async def debug_routes():
    """Debug endpoint to see all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods)
            })
    return {
        "registered_routes": routes,
        "total_routes": len(routes),
        "server_version": "5.0.0"
    }

# Fixed test endpoint
@app.get("/test/ollama")
async def test_ollama():
    """Test Ollama connection and return raw response"""
    try:
        import ollama
        client = ollama.Client()
        
        # Test basic connection
        models_result = client.list()
        
        # Test loaded models using our fixed function
        loaded_models_result = get_loaded_models()
        
        return {
            "success": True,
            "models_response": models_result,
            "loaded_models_response": loaded_models_result,
            "connection_status": "healthy",
            "available_client_methods": [method for method in dir(client) if not method.startswith('_')]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "connection_status": "failed"
        }

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
        
        # Generate research result using model conductor
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
                "timestamp": datetime.now(),
                "complexity": request.complexity,
                "config": jobs[job_id]["config"]
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
        "version": "5.0.0",
        "description": "Local AI-powered research agent with intelligent model selection",
        "features": [
            "Multi-model orchestration",
            "Intelligent model selection",
            "Background research processing",
            "Resource optimization for M4 Pro",
            "Cost-free local operation",
            "Robust error handling",
            "Advanced analytics",
            "Fixed Ollama PS integration"
        ],
        "endpoints": {
            "health": "/health",
            "status": "/status", 
            "chat": "/chat",
            "research": "/research",
            "models": "/models",
            "analytics": "/analytics",
            "debug": "/debug/routes",
            "test": "/test/ollama"
        },
        "documentation": "/docs",
        "current_time": datetime.now(),
        "server_info": {
            "host": "localhost",
            "port": 8001,
            "environment": "development"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Research Agent API Server v5...")
    print("📖 API Documentation: http://localhost:8001/docs")
    print("🔍 Health Check: http://localhost:8001/health")
    print("💬 Chat Test: http://localhost:8001/")
    print("📊 Analytics: http://localhost:8001/analytics")
    print("🔧 Debug Routes: http://localhost:8001/debug/routes")
    print("🧪 Test Ollama: http://localhost:8001/test/ollama")
    
    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=8001,  # Using port 8001 to avoid conflicts
        reload=True,
        log_level="info"
    )
