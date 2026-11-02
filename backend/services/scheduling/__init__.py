"""
RailSync OS CPU Scheduling Engine (Architecture Stub)
---------------------------------------------------
Course: Operating Systems - IASWE204

This module is designed to hold the explicit application-level CPU scheduling engine.
Booking requests are treated as processes / tasks that enter a ready queue:
  1. First-Come, First-Served (FCFS)
  2. Shortest Job First (SJF - based on passenger count / burst time estimation)
  3. Priority Scheduling (e.g., Tatkal / Senior Citizen / VIP priority queues)

The scheduler dispatches eligible booking processes to the Reservation Processor
in strict algorithmic order, calculating metrics such as:
  - Waiting Time
  - Turnaround Time
  - Throughput
"""

class SchedulingEnginePlaceholder:
    def __init__(self):
        self.active_algorithm = "FCFS"
        self.ready_queue = []

    def get_status(self):
        return {
            "algorithm": self.active_algorithm,
            "queue_length": len(self.ready_queue),
            "state": "initialized"
        }
