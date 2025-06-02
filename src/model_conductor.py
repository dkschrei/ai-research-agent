# src/model_conductor.py
"""
Model Selection Conductor - Intelligent model routing based on task complexity and cost
This is the "brain" that decides which model to use for each task
"""

import ollama
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import json

class ModelConductor:
    """Intelligent model selection and resource management"""
    
    def __init__(self):
        self.client = ollama.Client()
        
        # Model capabilities and performance data
        self.model_profiles = {
            "llama3.1:8b": {
                "size_gb": 5,
                "speed_score": 10,  # Based on your 1.85s benchmark
                "quality_score": 7,
                "cost_score": 10,   # Free local model
                "specialties": ["general", "fast_processing", "document_parsing"],
                "max_context": 4096
            },
            "qwen2.5:7b": {
                "size_gb": 4,
                "speed_score": 4,   # Based on your 14.56s benchmark
                "quality_score": 8,
                "cost_score": 10,   # Free local model
                "specialties": ["writing", "creative", "report_generation"],
                "max_context": 8192
            },
            "gemma2:9b": {
                "size_gb": 6,
                "speed_score": 4,   # Based on your 15.63s benchmark
                "quality_score": 8,
                "cost_score": 10,   # Free local model
                "specialties": ["reasoning", "analysis", "research"],
                "max_context": 8192
            },
            "deepseek-r1:8b": {
                "size_gb": 5,
                "speed_score": 2,   # Based on your 24.89s benchmark
                "quality_score": 9,
                "cost_score": 10,   # Free local model
                "specialties": ["complex_reasoning", "math", "coding"],
                "max_context": 4096
            },
            "gemma2:2b": {
                "size_gb": 1.6,
                "speed_score": 9,
                "quality_score": 6,
                "cost_score": 10,   # Free local model
                "specialties": ["simple_tasks", "quick_responses"],
                "max_context": 2048
            }
        }
        
        # Task complexity definitions
        self.task_complexity = {
            "simple": {
                "examples": ["document_parsing", "quick_questions", "classification"],
                "preferred_models": ["llama3.1:8b", "gemma2:2b"],
                "max_response_time": 5,
                "priority": "speed"
            },
            "standard": {
                "examples": ["research_synthesis", "basic_analysis", "summarization"],
                "preferred_models": ["llama3.1:8b", "qwen2.5:7b", "gemma2:9b"],
                "max_response_time": 20,
                "priority": "balanced"
            },
            "complex": {
                "examples": ["deep_analysis", "creative_writing", "multi_step_reasoning"],
                "preferred_models": ["gemma2:9b", "qwen2.5:7b", "deepseek-r1:8b"],
                "max_response_time": 60,
                "priority": "quality"
            },
            "critical": {
                "examples": ["executive_reports", "final_analysis", "client_deliverables"],
                "preferred_models": ["deepseek-r1:8b", "gemma2:9b"],
                "max_response_time": 120,
                "priority": "quality"
            }
        }
        
        # Task type to model mapping
        self.task_types = {
            "chat": "simple",
            "document_processing": "simple", 
            "web_research": "standard",
            "rag_query": "standard",
            "analysis": "complex",
            "writing": "complex",
            "research": "complex",
            "executive_report": "critical"
        }
        
        # Resource tracking
        self.max_memory_gb = 20  # Reserve 20GB for models on your M4 Pro
        self.usage_stats = {}
        self.cost_tracking = {
            "daily_limit": 2.0,      # $2/day for premium APIs (if any)
            "monthly_limit": 15.0,   # $15/month budget
            "current_spend": 0.0     # Track premium API usage
        }
        
    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama"""
        try:
            models = self.client.list()
            return [model['name'] for model in models['models']]
        except Exception as e:
            print(f"Error getting available models: {e}")
            return list(self.model_profiles.keys())
    
    def get_loaded_models(self) -> Dict[str, Dict]:
        """Get currently loaded models and their status"""
        try:
            ps_result = self.client.ps()
            loaded = {}
            
            for model in ps_result.get('models', []):
                model_name = model.get('name', 'unknown')
                loaded[model_name] = {
                    'size': model.get('size', 0),
                    'processor': model.get('processor', 'unknown'),
                    'until': model.get('until', 'unknown')
                }
            
            return loaded
        except Exception as e:
            print(f"Error getting loaded models: {e}")
            return {}
    
    def estimate_memory_usage(self) -> float:
        """Estimate current memory usage by loaded models"""
        loaded_models = self.get_loaded_models()
        total_memory = 0
        
        for model_name in loaded_models.keys():
            if model_name in self.model_profiles:
                total_memory += self.model_profiles[model_name]["size_gb"]
        
        return total_memory
    
    def can_load_model(self, model_name: str) -> bool:
        """Check if we have enough memory to load a model"""
        if model_name not in self.model_profiles:
            return True  # Unknown model, assume it's okay
        
        current_usage = self.estimate_memory_usage()
        needed_memory = self.model_profiles[model_name]["size_gb"]
        
        return (current_usage + needed_memory) <= self.max_memory_gb
    
    def select_model(self, 
                    task_type: str, 
                    complexity: Optional[str] = None,
                    preferred_model: Optional[str] = None,
                    max_response_time: Optional[int] = None,
                    context_length: Optional[int] = None) -> str:
        """
        Select the best model for a given task
        
        Args:
            task_type: Type of task (chat, research, analysis, etc.)
            complexity: Task complexity (simple, standard, complex, critical)
            preferred_model: User's preferred model (if any)
            max_response_time: Maximum acceptable response time in seconds
            context_length: Required context length
            
        Returns:
            Best model name for the task
        """
        
        # Determine complexity if not provided
        if complexity is None:
            complexity = self.task_types.get(task_type, "standard")
        
        # Get available models
        available_models = self.get_available_models()
        
        # If user has a preference and it's available, try to use it
        if preferred_model and preferred_model in available_models:
            if self.can_load_model(preferred_model):
                return preferred_model
        
        # Get candidate models based on complexity
        complexity_config = self.task_complexity.get(complexity, self.task_complexity["standard"])
        preferred_models = complexity_config["preferred_models"]
        
        # Filter candidates by availability and resource constraints
        candidates = []
        for model in preferred_models:
            if model in available_models and self.can_load_model(model):
                candidates.append(model)
        
        # If no preferred models available, consider all available models
        if not candidates:
            candidates = [m for m in available_models if self.can_load_model(m)]
        
        # If still no candidates, return the fastest small model
        if not candidates:
            return "llama3.1:8b"  # Your fastest model as fallback
        
        # Score candidates based on task requirements
        scored_candidates = []
        for model in candidates:
            score = self._score_model_for_task(model, complexity, max_response_time, context_length)
            scored_candidates.append((model, score))
        
        # Sort by score and return the best
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_model = scored_candidates[0][0]
        
        # Log the decision
        self._log_model_selection(task_type, complexity, best_model, scored_candidates)
        
        return best_model
    
    def _score_model_for_task(self, 
                             model: str, 
                             complexity: str, 
                             max_response_time: Optional[int],
                             context_length: Optional[int]) -> float:
        """Score a model for a specific task"""
        
        if model not in self.model_profiles:
            return 0.5  # Unknown model gets neutral score
        
        profile = self.model_profiles[model]
        complexity_config = self.task_complexity[complexity]
        
        score = 0.0
        
        # Speed scoring (higher is better)
        if complexity_config["priority"] == "speed":
            score += profile["speed_score"] * 0.4
        elif complexity_config["priority"] == "balanced":
            score += profile["speed_score"] * 0.2
        else:  # quality priority
            score += profile["speed_score"] * 0.1
        
        # Quality scoring (higher is better)
        if complexity_config["priority"] == "quality":
            score += profile["quality_score"] * 0.4
        elif complexity_config["priority"] == "balanced":
            score += profile["quality_score"] * 0.3
        else:  # speed priority
            score += profile["quality_score"] * 0.2
        
        # Cost scoring (always prefer free local models)
        score += profile["cost_score"] * 0.2
        
        # Specialty bonus
        specialty_bonus = 0.0
        if complexity in ["simple"]:
            if "fast_processing" in profile["specialties"]:
                specialty_bonus += 0.1
        elif complexity in ["complex", "critical"]:
            if any(spec in profile["specialties"] for spec in ["reasoning", "analysis", "writing"]):
                specialty_bonus += 0.1
        
        score += specialty_bonus
        
        # Response time penalty
        if max_response_time:
            estimated_time = 30 / profile["speed_score"]  # Rough estimate
            if estimated_time > max_response_time:
                score -= 0.2
        
        # Context length requirement
        if context_length and context_length > profile["max_context"]:
            score -= 0.3
        
        return score
    
    def _log_model_selection(self, task_type: str, complexity: str, selected_model: str, candidates: List[Tuple[str, float]]):
        """Log model selection decision for analysis"""
        timestamp = datetime.now()
        
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "task_type": task_type,
            "complexity": complexity,
            "selected_model": selected_model,
            "candidates": {model: score for model, score in candidates},
            "reasoning": f"Selected {selected_model} for {task_type} task with {complexity} complexity"
        }
        
        # Store in usage stats
        if selected_model not in self.usage_stats:
            self.usage_stats[selected_model] = []
        
        self.usage_stats[selected_model].append(log_entry)
        
        # Keep only last 100 entries per model
        if len(self.usage_stats[selected_model]) > 100:
            self.usage_stats[selected_model] = self.usage_stats[selected_model][-100:]
    
    def get_model_recommendations(self, task_description: str) -> Dict[str, str]:
        """Get model recommendations for a task description"""
        
        # Simple keyword-based task classification
        task_description_lower = task_description.lower()
        
        # Determine task type and complexity
        if any(word in task_description_lower for word in ["quick", "simple", "fast", "parse"]):
            task_type = "simple"
            complexity = "simple"
        elif any(word in task_description_lower for word in ["analyze", "research", "investigate"]):
            task_type = "analysis"
            complexity = "complex"
        elif any(word in task_description_lower for word in ["write", "report", "create", "generate"]):
            task_type = "writing"
            complexity = "complex"
        elif any(word in task_description_lower for word in ["executive", "critical", "important", "final"]):
            task_type = "executive_report"
            complexity = "critical"
        else:
            task_type = "general"
            complexity = "standard"
        
        # Get recommendations
        primary = self.select_model(task_type, complexity)
        
        # Get alternatives
        available = self.get_available_models()
        alternatives = [m for m in available if m != primary and self.can_load_model(m)][:2]
        
        return {
            "primary_recommendation": primary,
            "alternatives": alternatives,
            "reasoning": f"Based on task type '{task_type}' with '{complexity}' complexity",
            "estimated_performance": self._get_performance_estimate(primary)
        }
    
    def _get_performance_estimate(self, model: str) -> Dict[str, str]:
        """Get performance estimate for a model"""
        if model not in self.model_profiles:
            return {"response_time": "unknown", "quality": "unknown"}
        
        profile = self.model_profiles[model]
        
        # Convert speed score to estimated response time
        if profile["speed_score"] >= 8:
            response_time = "Very Fast (1-5s)"
        elif profile["speed_score"] >= 6:
            response_time = "Fast (5-15s)"
        elif profile["speed_score"] >= 4:
            response_time = "Moderate (15-30s)"
        else:
            response_time = "Slow (30s+)"
        
        # Convert quality score to description
        if profile["quality_score"] >= 8:
            quality = "High Quality"
        elif profile["quality_score"] >= 6:
            quality = "Good Quality"
        else:
            quality = "Basic Quality"
        
        return {
            "response_time": response_time,
            "quality": quality,
            "specialties": ", ".join(profile["specialties"])
        }
    
    def get_usage_analytics(self) -> Dict[str, any]:
        """Get usage analytics and recommendations"""
        total_requests = sum(len(requests) for requests in self.usage_stats.values())
        
        if total_requests == 0:
            return {"message": "No usage data available yet"}
        
        # Model usage frequency
        model_usage = {
            model: len(requests) 
            for model, requests in self.usage_stats.items()
        }
        
        # Most used model
        most_used = max(model_usage.keys(), key=lambda k: model_usage[k]) if model_usage else None
        
        return {
            "total_requests": total_requests,
            "model_usage_frequency": model_usage,
            "most_used_model": most_used,
            "memory_usage": {
                "current_estimated": f"{self.estimate_memory_usage():.1f}GB",
                "max_allocated": f"{self.max_memory_gb}GB",
                "utilization": f"{(self.estimate_memory_usage() / self.max_memory_gb) * 100:.1f}%"
            },
            "cost_tracking": self.cost_tracking,
            "recommendations": self._get_optimization_recommendations()
        }
    
    def _get_optimization_recommendations(self) -> List[str]:
        """Get optimization recommendations based on usage patterns"""
        recommendations = []
        
        current_memory = self.estimate_memory_usage()
        
        if current_memory > self.max_memory_gb * 0.8:
            recommendations.append("Consider unloading unused models to free memory")
        
        if current_memory < self.max_memory_gb * 0.3:
            recommendations.append("You have plenty of memory - consider loading larger models for better quality")
        
        # Check for model usage patterns
        if self.usage_stats:
            total_requests = sum(len(requests) for requests in self.usage_stats.values())
            if total_requests > 10:
                # Find underused models
                for model, requests in self.usage_stats.items():
                    if len(requests) / total_requests < 0.05:  # Used less than 5%
                        recommendations.append(f"Model {model} is rarely used - consider unloading")
        
        return recommendations
