#!/bin/bash
# monitor_resources.sh - Monitor M4 Pro resource usage

echo "🖥️  M4 Pro Resource Monitor"
echo "=========================="

# Memory usage
echo "💾 Memory Usage:"
memory_info=$(vm_stat | awk '
/Pages free/ { free = $3 }
/Pages active/ { active = $3 }
/Pages inactive/ { inactive = $3 }
/Pages wired down/ { wired = $4 }
END {
    free_gb = (free * 4096) / (1024^3)
    used_gb = ((active + inactive + wired) * 4096) / (1024^3)
    total_gb = free_gb + used_gb
    printf "  Used: %.1fGB / %.1fGB (%.1f%%)\n", used_gb, total_gb, (used_gb/total_gb)*100
}')
echo "$memory_info"

# CPU usage
echo "🔥 CPU Usage:"
cpu_info=$(top -l 1 -n 0 | grep "CPU usage" | awk '{print "  " $3 " user, " $5 " system, " $7 " idle"}')
echo "$cpu_info"

# Ollama processes
echo "🤖 Ollama Status:"
if pgrep -x "ollama" > /dev/null; then
    ollama_memory=$(ps -o pid,rss,command -p $(pgrep ollama) | tail -n +2 | awk '{rss_gb = $2/1024/1024; printf "  PID %s: %.1fGB RAM\n", $1, rss_gb}')
    echo "$ollama_memory"
    echo "  Models loaded:"
    ollama ps | tail -n +2 | awk '{printf "    %s (%s)\n", $1, $2}'
else
    echo "  Ollama not running"
fi

# Docker containers
echo "🐳 Docker Containers:"
if docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -q research; then
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep research
else
    echo "  No research containers running"
fi

# GPU usage (if available)
echo "🎮 GPU Status:"
gpu_info=$(system_profiler SPDisplaysDataType | grep -A 5 "Metal" | head -3)
if [ -n "$gpu_info" ]; then
    echo "  Metal GPU available"
else
    echo "  No GPU info available"
fi

echo ""
echo "💡 Resource Tips:"
echo "  - Keep total memory usage under 40GB"
echo "  - Monitor CPU temperature during long runs"
echo "  - Use 'ollama ps' to see loaded models"
echo "  - Run 'docker system prune' to free up space"
