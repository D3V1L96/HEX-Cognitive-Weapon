import os
import json
import time
import logging
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='[Evolution] %(message)s')
logger = logging.getLogger(__name__)
class EvolutionMemory:
    """Tracks user behavior patterns and identifies automation gaps."""

    MEMORY_FILE = os.path.join(os.getcwd(), "hex_evolution_memory.json")

    def __init__(self):
        self.data = self._load()
        self.lock = threading.Lock()

    def _load(self):
        if os.path.exists(self.MEMORY_FILE):
            try:
                with open(self.MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "command_history": [],
            "repeated_patterns": {},
            "failed_commands": [],
            "user_corrections": [],
            "created_agents": [],
            "evolution_log": []
        }

    def _save(self):
        with self.lock:
            try:
                with open(self.MEMORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
            except Exception as e:
                logger.error(f"Evolution memory save failed: {e}")

    def record_command(self, command: str, agent_used: str, success: bool):
        """Record every command for pattern analysis."""
        entry = {
            "command": command,
            "agent": agent_used,
            "success": success,
            "timestamp": time.time(),
            "hour": datetime.now().hour,
            "day": datetime.now().weekday()
        }

        self.data["command_history"].append(entry)

        if len(self.data["command_history"]) > 500:
            self.data["command_history"] = self.data["command_history"][-500:]

        key = command.lower().strip()[:50]
        self.data["repeated_patterns"][key] = \
            self.data["repeated_patterns"].get(key, 0) + 1

        if not success:
            self.data["failed_commands"].append({
                "command": command,
                "timestamp": time.time()
            })
            if len(self.data["failed_commands"]) > 100:
                self.data["failed_commands"] = self.data["failed_commands"][-100:]

        self._save()

    def get_frequent_patterns(self, min_count=3):
        """Find commands user repeats frequently."""
        return {
            cmd: count
            for cmd, count in self.data["repeated_patterns"].items()
            if count >= min_count
        }

    def get_failed_patterns(self):
        """Find commands that consistently fail."""
        fail_counts = {}
        for entry in self.data["failed_commands"]:
            key = entry["command"].lower().strip()[:50]
            fail_counts[key] = fail_counts.get(key, 0) + 1
        return {cmd: count for cmd, count in fail_counts.items() if count >= 2}

    def get_time_patterns(self):
        """Find time-based usage patterns."""
        hour_counts = {}
        for entry in self.data["command_history"]:
            h = entry.get("hour", 0)
            hour_counts[h] = hour_counts.get(h, 0) + 1
        return hour_counts

    def log_evolution(self, event_type: str, details: dict):
        """Log evolution events."""
        self.data["evolution_log"].append({
            "type": event_type,
            "details": details,
            "timestamp": time.time()
        })
        if len(self.data["evolution_log"]) > 200:
            self.data["evolution_log"] = self.data["evolution_log"][-200:]
        self._save()


class AgentDesigner:
    """Uses LLM to design and generate new agent code autonomously."""

    AGENTS_DIR = os.path.join(os.getcwd(), "hex_dynamic_agents")

    def __init__(self):
        os.makedirs(self.AGENTS_DIR, exist_ok=True)

    @staticmethod
    def design_agent(gap_description: str, examples: list) -> dict:
        """Ask LLM to design a new agent based on observed gap."""
        import requests

        examples_text = "\n".join([f"- {ex}" for ex in examples[:5]])

        prompt = (
            "You are an AI Agent Architect. Analyze this automation gap and design a specialized agent.\n\n"
            f"OBSERVED GAP: {gap_description}\n\n"
            f"EXAMPLE COMMANDS FROM USER:\n{examples_text}\n\n"
            "EXISTING AGENTS: Research, Code, Reminder, System, Conversation\n\n"
            "DESIGN A NEW AGENT THAT:\n"
            "1. Has a clear single responsibility\n"
            "2. Can handle the observed gap autonomously\n"
            "3. Integrates with existing HEX modules\n\n"
            "Respond in EXACTLY this JSON format (no markdown, no explanation):\n"
            '{\n'
            '    "name": "AgentName",\n'
            '    "description": "What it does",\n'
            '    "trigger_keywords": ["keyword1", "keyword2"],\n'
            '    "required_modules": ["module1"],\n'
            '    "methods": [\n'
            '        {"name": "method_name", "description": "what it does", "logic": "pseudocode"}\n'
            '    ],\n'
            '    "priority": "high"\n'
            '}'
        )

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 800}
                },
                timeout=60
            )

            if resp.status_code == 200:
                response = resp.json().get("response", "").strip()
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                    spec = json.loads(json_str)
                    logger.info(f"[Designer] Agent designed: {spec.get('name', 'Unknown')}")
                    return spec

        except json.JSONDecodeError as e:
            logger.error(f"[Designer] JSON parse failed: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[Designer] Request failed: {e}")
        except Exception as e:
            logger.error(f"[Designer] Design failed: {e}")

        return {}

    @staticmethod
    def generate_agent_code(spec: dict) -> str:
        """Generate Python code for the designed agent."""
        import requests

        if not spec or not spec.get("name"):
            return ""

        name = spec.get("name", "DynamicAgent")
        desc = spec.get("description", "")
        keywords = spec.get("trigger_keywords", [])
        modules = spec.get("required_modules", [])
        methods = spec.get("methods", [])

        methods_desc = ""
        for m in methods:
            methods_desc += (
                f"\n    Method: {m.get('name', 'unknown')}"
                f"\n    Description: {m.get('description', '')}"
                f"\n    Logic: {m.get('logic', '')}\n"
            )

        prompt = (
            "Generate a complete Python class for a HEX AI agent.\n\n"
            f"AGENT SPEC:\n"
            f"- Name: {name}\n"
            f"- Description: {desc}\n"
            f"- Trigger Keywords: {keywords}\n"
            f"- Required Modules: {modules}\n"
            f"- Methods: {methods_desc}\n\n"
            "RULES:\n"
            f"- Class name must be {name}Agent\n"
            "- Include __init__, can_handle, and execute methods\n"
            "- can_handle checks trigger_keywords against task string\n"
            "- execute returns dict with keys: agent, content, success\n"
            "- Use try-except for error handling\n"
            "- Import only standard library + listed modules\n"
            "- NO markdown backticks, NO explanation, ONLY raw Python code\n"
            "- Include all necessary imports at top\n\n"
            "Generate the complete .py file content:"
        )

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 1500}
                },
                timeout=90
            )

            if resp.status_code == 200:
                code = resp.json().get("response", "").strip()
                if "```" in code:
                    parts = code.split("```")
                    code = parts[1] if len(parts) > 1 else code
                    code = code.replace("python", "").strip()

                logger.info(f"[Generator] Code generated for {name} ({len(code)} chars)")
                return code

        except requests.exceptions.RequestException as e:
            logger.error(f"[Generator] Request failed: {e}")
        except Exception as e:
            logger.error(f"[Generator] Code generation failed: {e}")

        return ""

    def save_and_register(self, name: str, code: str) -> bool:
        """Save agent code to dynamic agents directory."""
        if not code or not name:
            return False

        try:
            filename = f"{name.lower()}_agent.py"
            filepath = os.path.join(self.AGENTS_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            logger.info(f"[Registry] Saved: {filepath}")
            return True

        except Exception as e:
            logger.error(f"[Registry] Save failed: {e}")
            return False


class GapAnalyzer:
    """Autonomously detects automation gaps from user behavior."""

    def __init__(self, memory: EvolutionMemory):
        self.memory = memory

    def analyze(self) -> list:
        """Analyze patterns and return list of detected gaps."""
        gaps = []

        # 1. High-frequency repeated commands
        frequent = self.memory.get_frequent_patterns(min_count=5)
        existing_agents = ["research", "code", "reminder", "system", "conversation"]

        for cmd, count in frequent.items():
            is_covered = any(agent in cmd for agent in existing_agents)
            if not is_covered and count >= 5:
                gaps.append({
                    "type": "repeated_task",
                    "description": f"User frequently runs: '{cmd}' ({count} times)",
                    "examples": [cmd],
                    "frequency": count,
                    "priority": "high" if count >= 10 else "medium"
                })

        # 2. Consistently failing commands
        failed = self.memory.get_failed_patterns()
        for cmd, count in failed.items():
            if count >= 2:
                gaps.append({
                    "type": "failed_task",
                    "description": f"Command fails repeatedly: '{cmd}' ({count} failures)",
                    "examples": [cmd],
                    "failure_count": count,
                    "priority": "high"
                })

        # 3. Time-based patterns
        time_patterns = self.memory.get_time_patterns()
        peak_hours = [h for h, c in time_patterns.items() if c >= 10]
        if peak_hours:
            peak_commands = {}
            for entry in self.memory.data["command_history"]:
                if entry.get("hour") in peak_hours:
                    cmd_key = entry["command"].lower().strip()[:50]
                    peak_commands[cmd_key] = peak_commands.get(cmd_key, 0) + 1

            for cmd, count in peak_commands.items():
                if count >= 5:
                    gaps.append({
                        "type": "time_pattern",
                        "description": f"At hours {peak_hours}, user often: '{cmd}' ({count} times)",
                        "examples": [cmd],
                        "peak_hours": peak_hours,
                        "priority": "medium"
                    })

        priority_order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: priority_order.get(g.get("priority", "low"), 2))

        return gaps


class SelfEvolutionEngine:
    """
    Fully Autonomous Evolution Engine.
    Observes -> Detects Gaps -> Designs Agents -> Generates Code -> Registers -> Learns
    """
    _instance = None

    EVOLUTION_INTERVAL = 300  # Check every 5 minutes
    MIN_COMMANDS_BEFORE_EVOLUTION = 20

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.memory = EvolutionMemory()
        self.analyzer = GapAnalyzer(self.memory)
        self.designer = AgentDesigner()
        self.running = False
        self.evolution_thread = None
        self.speak_callback = None
        self.created_agents = set()

        self._initialized = True
        logger.info("Self-Evolution Engine Initialized")

    def set_speak_callback(self, callback):
        self.speak_callback = callback

    def record_interaction(self, command: str, agent_used: str, success: bool):
        """Call this after every command execution."""
        self.memory.record_command(command, agent_used, success)

    def start(self):
        """Start autonomous evolution loop."""
        if self.running:
            return

        self.running = True
        self.evolution_thread = threading.Thread(
            target=self._evolution_loop, daemon=True
        )
        self.evolution_thread.start()
        logger.info("Self-Evolution Engine Started")

    def stop(self):
        self.running = False
        if self.evolution_thread:
            self.evolution_thread.join(timeout=10)
        logger.info("Self-Evolution Engine Stopped")

    def _evolution_loop(self):
        """Main autonomous evolution cycle."""
        while self.running:
            try:
                time.sleep(self.EVOLUTION_INTERVAL)

                total_commands = len(self.memory.data["command_history"])
                if total_commands < self.MIN_COMMANDS_BEFORE_EVOLUTION:
                    continue

                logger.info(f"[Evolution] Analyzing {total_commands} recorded interactions...")

                gaps = self.analyzer.analyze()

                if not gaps:
                    logger.info("[Evolution] No significant gaps detected")
                    continue

                top_gap = gaps[0]
                gap_desc = top_gap["description"]

                gap_key = gap_desc[:30].lower()
                if gap_key in self.created_agents:
                    continue

                logger.info(f"[Evolution] Gap detected: {gap_desc}")

                spec = self.designer.design_agent(
                    gap_desc,
                    top_gap.get("examples", [])
                )

                if not spec or not spec.get("name"):
                    logger.warning("[Evolution] Agent design failed, skipping")
                    continue

                agent_name = spec["name"]

                code = self.designer.generate_agent_code(spec)

                if not code or len(code) < 100:
                    logger.warning("[Evolution] Code generation failed, skipping")
                    continue

                success = self.designer.save_and_register(agent_name, code)

                if success:
                    self.created_agents.add(gap_key)

                    self.memory.log_evolution("agent_created", {
                        "agent_name": agent_name,
                        "gap": gap_desc,
                        "spec": spec
                    })

                    msg = (
                        f"Sir, I noticed you frequently need {gap_desc[:50]}. "
                        f"I've created a new {agent_name} agent to handle this autonomously."
                    )

                    if self.speak_callback:
                        self.speak_callback(msg)

                    logger.info(f"[Evolution] New agent created: {agent_name}")
                else:
                    logger.error(f"[Evolution] Failed to save agent: {agent_name}")

            except Exception as e:
                logger.error(f"[Evolution] Cycle error: {e}")
                time.sleep(30)

    def get_status(self) -> str:
        """Get evolution engine status."""
        total = len(self.memory.data["command_history"])
        agents_created = len(self.created_agents)
        gaps = len(self.analyzer.analyze())

        return (
            f"Evolution Status: {total} interactions analyzed, "
            f"{agents_created} agents auto-created, "
            f"{gaps} gaps currently detected."
        )

    def force_evolution(self) -> str:
        """Manually trigger evolution cycle."""
        gaps = self.analyzer.analyze()
        if not gaps:
            return "No automation gaps detected yet, Sir. Keep using HEX and I'll learn."

        results = []
        for gap in gaps[:3]:
            spec = self.designer.design_agent(gap["description"], gap.get("examples", []))
            if spec and spec.get("name"):
                code = self.designer.generate_agent_code(spec)
                if code and len(code) >= 100:
                    self.designer.save_and_register(spec["name"], code)
                    results.append(f"Created {spec['name']} for: {gap['description'][:50]}")
                else:
                    results.append(f"Code generation failed for: {gap['description'][:50]}")
            else:
                results.append(f"Design failed for: {gap['description'][:50]}")

        return "Evolution cycle complete, Sir:\n" + "\n".join(results)


# Global Singleton
hex_evolution = SelfEvolutionEngine()