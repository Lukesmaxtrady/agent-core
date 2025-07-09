# agent/god_manager_agent.py

import importlib
import os
import traceback
from termcolor import cprint, colored

AGENT_MODULES = [
    "planner", "coder", "tester", "deployer", "auto_upgrade_agent", "devops_fixer",
    "incident_responder", "supreme_auditor", "peer_review_agent", "knowledgebase_agent",
    "metrics_collector", "rollback", "root_cause_analytics", "llm_codegen", "llm_router",
    "llm_selector_dashboard", "plugin_loader", "plugin_hot_reload_daemon", "project_wizard_agent",
    "onboarding_agent", "super_devops_agent", "deploy_tools", "event_bus", "context_loader", "feedback"
]

def load_agent_modules(base_path="agent"):
    agents = {}
    for mod_name in AGENT_MODULES:
        try:
            mod = importlib.import_module(f"{base_path}.{mod_name}")
            agents[mod_name] = mod
        except Exception as e:
            cprint(f"[Warning] Could not load agent: {mod_name} - {e}", "yellow")
    return agents

class GodManagerAgent:
    def __init__(self):
        cprint("🔱 Initializing God Manager Agent — Orchestrator of All Agents", "magenta", attrs=["bold"])
        self.agents = load_agent_modules()
        self._register_workflows()
    
    def _register_workflows(self):
        self.workflows = {
            "build": ["planner", "coder", "tester"],
            "upgrade_all": ["auto_upgrade_agent"],
            "deploy": ["deployer"],
            "devops_fix": ["devops_fixer"],
            "incident_response": ["incident_responder"],
            "audit": ["supreme_auditor"],
            "peer_review": ["peer_review_agent"],
            "knowledgebase": ["knowledgebase_agent"],
            "metrics": ["metrics_collector"],
            "rollback": ["rollback"],
            "project_wizard": ["project_wizard_agent"],
        }
    
    def run_workflow(self, workflow, *args, **kwargs):
        steps = self.workflows.get(workflow)
        if not steps:
            cprint(f"[Error] No such workflow: {workflow}", "red")
            return
        cprint(f"\n🚦 Running workflow: {workflow}", "cyan", attrs=["bold"])
        for agent_name in steps:
            agent = self.agents.get(agent_name)
            if agent:
                try:
                    cprint(f"→ Calling agent: {agent_name}", "yellow")
                    # Prefer main_entry, fallback to main()
                    if hasattr(agent, "main_entry"):
                        agent.main_entry(*args, **kwargs)
                    elif hasattr(agent, "main"):
                        agent.main(*args, **kwargs)
                    elif hasattr(agent, agent_name):
                        getattr(agent, agent_name)(*args, **kwargs)
                    else:
                        cprint(f"[Skip] No main entry found for {agent_name}.", "magenta")
                except Exception as e:
                    cprint(f"[FAIL] {agent_name} failed: {e}", "red")
                    traceback.print_exc()
                    # Optionally: escalate to peer review or roll back
            else:
                cprint(f"[Missing] Agent not loaded: {agent_name}", "red")
    
    def run_agent(self, agent_name, *args, **kwargs):
        agent = self.agents.get(agent_name)
        if not agent:
            cprint(f"[Error] Agent '{agent_name}' not loaded.", "red")
            return
        cprint(f"\n⚡ Running agent: {agent_name}", "cyan")
        try:
            if hasattr(agent, "main_entry"):
                return agent.main_entry(*args, **kwargs)
            elif hasattr(agent, "main"):
                return agent.main(*args, **kwargs)
            elif hasattr(agent, agent_name):
                return getattr(agent, agent_name)(*args, **kwargs)
            else:
                cprint(f"[Skip] No main entry found for {agent_name}.", "magenta")
        except Exception as e:
            cprint(f"[FAIL] {agent_name} failed: {e}", "red")
            traceback.print_exc()
    
    def list_agents(self):
        cprint("Registered agents:", "green")
        for name in sorted(self.agents.keys()):
            cprint(f"  - {name}", "yellow")
    
    def available_workflows(self):
        cprint("Available workflows:", "green")
        for wf in self.workflows:
            cprint(f"  - {wf}", "yellow")

if __name__ == "__main__":
    god = GodManagerAgent()
    god.available_workflows()
    god.list_agents()
    cprint("\nTry: god.run_workflow('build') or god.run_agent('project_wizard_agent')", "cyan")
