# Parallel Testing Enhancement Summary

## Overview

Enhanced the `dia-harness optimize` command to leverage **two levels of parallelism** for maximum performance during iterative optimization.

## Architecture

### Level 1: Parallel Training + Test Evaluations (NEW)

When both training and test sets are provided, the optimizer now runs them **in parallel** instead of sequentially.

**Before:**
```
[Train Eval] → [Test Eval]  # Sequential, 2x time
```

**After:**
```
[Train Eval]  # Parallel, ~1x time
[Test Eval]
```

### Level 2: Parallel Repeat Measurements (EXISTING)

Within each evaluation, all repeat measurements run in parallel using ThreadPoolExecutor.

**Example with 3 repeats:**
```
[Test 1 Rep 1] [Test 1 Rep 2] [Test 1 Rep 3]  # All parallel
[Test 2 Rep 1] [Test 2 Rep 2] [Test 2 Rep 3]  # All parallel
...
```

## Performance Impact

### Example Scenario:
- 10 training questions
- 5 test questions
- 3 repeats per test
- 10 max workers

**Before:**
1. Training: 30 tests (10 × 3) in parallel → ~T seconds
2. Test: 15 tests (5 × 3) in parallel → ~0.5T seconds
3. **Total: ~1.5T seconds**

**After:**
1. Training + Test both run in parallel
2. **Total: ~T seconds (max of the two)**
3. **~33-50% faster** depending on test set size

## Implementation Details

### New Method: `_run_parallel_evaluations()`

```python
def _run_parallel_evaluations(self) -> tuple:
    """Run training and test evaluations in parallel.

    Returns:
        Tuple of (train_results, train_metrics, train_failures,
                  test_results, test_metrics)
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both evaluation tasks
        train_future = executor.submit(self._run_evaluation)
        test_future = executor.submit(self._run_test_evaluation)

        # Wait for both to complete
        train_results, train_metrics, train_failures = train_future.result()
        test_results, test_metrics, test_failures = test_future.result()

    return train_results, train_metrics, train_failures, test_results, test_metrics
```

### Modified Flow in `run()` Method

```python
# Step 2: Run evaluations in parallel (training + test if provided)
if self.test_set_path:
    # Run both evaluations in parallel
    results, metrics, failures, test_results, test_metrics = self._run_parallel_evaluations()
else:
    # Only run training evaluation
    results, metrics, failures = self._run_evaluation()
    test_results, test_metrics = None, None
```

## Usage

No changes to CLI interface. The parallelism is automatic:

```bash
# Without test set - only training evaluation runs
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --num-repeats 3

# With test set - BOTH evaluations run in parallel
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --test-set data/test_set.json \
  --num-repeats 3
```

## Configuration

The `--max-workers` flag controls parallelism within each evaluation:

```bash
# Use 20 parallel workers for test execution
dia-harness optimize \
  --config-file configs/baseline_config.json \
  --golden-set data/golden_set.json \
  --test-set data/test_set.json \
  --num-repeats 3 \
  --max-workers 20
```

## Files Modified

1. **src/iterative/optimizer.py**
   - Added `ThreadPoolExecutor` import
   - Added `_run_parallel_evaluations()` method
   - Modified `run()` to use parallel evaluations when test set provided
   - Added clarifying docstrings

## Backward Compatibility

Fully backward compatible:
- Without `--test-set`: Behaves exactly as before
- With `--test-set`: Automatically uses parallel execution
- Single repeats (`--num-repeats 1`): Works as before
- All existing flags and options work unchanged

## Thread Safety

Both evaluator instances are independent:
- Separate `AgentClient` instances
- Separate output files (train vs test)
- Separate session management
- Thread-safe result aggregation using locks

## Benefits

1. **Performance**: 33-50% faster when using test sets
2. **Resource Utilization**: Better CPU/network utilization
3. **User Experience**: Faster iteration cycles
4. **Scalability**: Handles larger test suites efficiently

## Future Enhancements

Potential areas for further optimization:
- Parallel prompt improvement analysis
- Parallel deployment + first evaluation
- Async API calls within evaluator
- Distributed evaluation across multiple machines
