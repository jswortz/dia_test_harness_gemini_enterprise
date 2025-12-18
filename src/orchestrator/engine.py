import json
import time
import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from .agent_client import AgentClient

logger = logging.getLogger(__name__)

class TestEngine:
    def __init__(self, client: AgentClient, output_dir: str = "results"):
        self.client = client
        self.output_dir = output_dir

    def run_suite(self, configs: List[Dict], golden_set: List[Dict], parallel_agents: int = 1):
        """
        Runs the test suite across multiple configurations.
        
        Args:
            configs: List of agent configurations to test.
            golden_set: List of test cases (questions/expected results).
            parallel_agents: Number of agents to test in parallel (simulating concurrent tuning trials).
        """
        results = []
        
        # simple sequential loop for configs for now, but we could parallelize this too
        # using ThreadPoolExecutor if we wanted to deploy multiple agents at once.
        
        with ThreadPoolExecutor(max_workers=parallel_agents) as executor:
            future_to_config = {executor.submit(self.evaluate_configuration, config, golden_set): config for config in configs}
            
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    config_results = future.result()
                    results.extend(config_results)
                except Exception as e:
                    logger.error(f"Configuration {config.get('name')} failed: {e}")
                    
        return results

    def evaluate_configuration(self, config: Dict, golden_set: List[Dict]) -> List[Dict]:
        """Deploy agent, run tests, teardown, and return metrics."""
        agent_id = None
        results = []
        config_name = config.get('name', 'unknown')
        
        try:
            logger.info(f"[{config_name}] Deploying agent...")
            start_deploy = time.time()
            agent_id = self.client.create_agent(config)
            deploy_time = time.time() - start_deploy
            logger.info(f"[{config_name}] Deployed agent {agent_id} in {deploy_time:.2f}s")
            
            # Run Test Cases
            for case in golden_set:
                qid = case["question_id"]
                question = case["nl_question"]
                
                logger.debug(f"[{config_name}] Asking: {question}")
                start_ask = time.time()
                response = self.client.ask_question(agent_id, question)
                latency = time.time() - start_ask
                
                # Mock evaluation (Replace w/ robust SQL/Data comparison logic)
                # For now, we just pass if we got SQL back.
                generated_sql = response.get("sql", "")
                is_correct = len(generated_sql) > 0 # Super simple check
                
                results.append({
                    "config_name": config_name,
                    "agent_id": agent_id,
                    "question_id": qid,
                    "question": question,
                    "generated_sql": generated_sql,
                    "expected_sql": case.get("expected_sql", ""),
                    "is_correct": is_correct,
                    "latency": latency,
                    "deploy_time": deploy_time
                })
                
        except Exception as e:
            logger.error(f"[{config_name}] Error during evaluation: {e}")
            raise e
        finally:
            if agent_id:
                logger.info(f"[{config_name}] Tearing down agent {agent_id}...")
                self.client.delete_agent(agent_id)
                
        return results
