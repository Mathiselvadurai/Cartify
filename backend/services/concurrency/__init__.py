"""
RailSync Concurrency and Synchronization Primitives (Architecture Stub)
---------------------------------------------------------------------
Course: Operating Systems - IASWE204

This module manages synchronization controls to prevent race conditions
and duplicate seat bookings on shared train inventory resources:
  - Mutex Locks per train/coach resource
  - Counting Semaphores for concurrent query limiters
  - Critical Section isolation during seat assignment
"""
import threading

class TrainLockManager:
    def __init__(self):
        # Mutex locks indexed by train_id
        self._locks = {}
        self._global_lock = threading.Lock()

    def get_lock(self, train_id: int) -> threading.Lock:
        with self._global_lock:
            if train_id not in self._locks:
                self._locks[train_id] = threading.Lock()
            return self._locks[train_id]
