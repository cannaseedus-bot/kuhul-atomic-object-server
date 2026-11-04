#!/usr/bin/env python3
import json
import sys
import time


def process_data(parameters):
    """Example data processing function."""
    data = parameters.get('data', [])
    operation = parameters.get('operation', 'sum')

    if operation == 'sum':
        result = sum(data)
    elif operation == 'average':
        result = sum(data) / len(data) if data else 0
    elif operation == 'max':
        result = max(data) if data else 0
    elif operation == 'min':
        result = min(data) if data else 0
    else:
        result = None

    return result


if __name__ == "__main__":
    try:
        task_json = sys.stdin.readline().strip()
        task = json.loads(task_json)

        print(f"Worker started for task {task['task_id']}", flush=True)

        time.sleep(2)

        result = process_data(task['parameters'])

        result_data = {
            'task_id': task['task_id'],
            'result': result,
            'status': 'completed'
        }

        print(f"RESULT:{json.dumps(result_data)}", flush=True)

    except Exception as exc:
        error_data = {
            'task_id': task.get('task_id', 'unknown'),
            'error': str(exc),
            'status': 'failed'
        }
        print(f"ERROR:{json.dumps(error_data)}", flush=True)
        sys.exit(1)
