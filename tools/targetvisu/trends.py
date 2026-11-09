# SPDX-License-Identifier: GPL-3.0-only
"""Bounded in-memory time-series history, independent of PLC scan and GUI threads."""
from collections import deque
import math


class TrendStore:
    """Collect numeric PLC snapshots on the TargetVisu service polling thread."""

    def __init__(self, document):
        self.screens = {}
        self.configs = {}
        self.samples = {}
        self.next_due = {}
        for screen in document['screens']:
            self.screens[screen['id']] = []
            for element in screen['elements']:
                if element['kind'] != 'trend':
                    continue
                config = element['trend']
                identifier = element['id']
                self.configs[identifier] = config
                self.screens[screen['id']].append(identifier)
                max_points = math.ceil(config['durationSec'] * 1000 / config['sampleMs']) + 1
                self.samples[identifier] = deque(maxlen=min(601, max_points))

    def capture(self, monotonic_seconds, unix_seconds, values):
        """Capture at the configured interval, without backfilling missed polls."""
        for identifier, config in self.configs.items():
            if monotonic_seconds < self.next_due.get(identifier, -math.inf):
                continue
            sample = []
            for curve in config['series']:
                value = values.get(curve['path'].lower())
                if type(value) not in (int, float) or not math.isfinite(value):
                    break
                sample.append(value)
            else:
                self.samples[identifier].append([round(unix_seconds, 3), *sample])
                self.next_due[identifier] = monotonic_seconds + config['sampleMs'] / 1000

    def for_screen(self, screen_id, unix_seconds):
        if screen_id not in self.screens:
            raise ValueError('Unknown Trend screen')
        result = {}
        for identifier in self.screens[screen_id]:
            config = self.configs[identifier]
            cutoff = unix_seconds - config['durationSec']
            result[identifier] = [point for point in self.samples[identifier]
                                  if cutoff <= point[0] <= unix_seconds + 1]
        return result
