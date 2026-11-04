#!/usr/bin/env python3
import json
import sys
import time


def capture_metrics(parameters):
    """Return a basic monitoring payload."""
    return {
        'service': parameters.get('service', 'unknown'),
        'status': parameters.get('status', 'ok'),
        'latency_ms': parameters.get('latency_ms', 0),
        'timestamp': time.time()
    }


if __name__ == "__main__":
    try:
        task_json = sys.stdin.readline().strip()
        task = json.loads(task_json)

        print(f"Monitor worker started for {task['task_id']}", flush=True)
        time.sleep(0.5)

        result = capture_metrics(task['parameters'])

        result_data = {
            'task_id': task['task_id'],
            'result': result,
            'status': 'completed'
        }

        print(f"RESULT:{json.dumps(result_data)}", flush=True)

    except Exception as exc:
        error_data = {'error': str(exc)}
        print(f"ERROR:{json.dumps(error_data)}", flush=True)
        sys.exit(1)
