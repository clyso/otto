#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2010 Bitly
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Generate a text format histogram

This is a loose port to python of the Perl version at
http://www.pandamatak.com/people/anand/xfer/histo

https://github.com/bitly/data_hacks
"""

from decimal import Decimal
import math
from optparse import OptionParser
from collections import namedtuple


class MVSD(object):
    "A class that calculates a running Mean / Variance / Standard Deviation"
    def __init__(self):
        self.is_started = False
        self.ss = Decimal(0)  # (running) sum of square deviations from mean
        self.m = Decimal(0)  # (running) mean
        self.total_w = Decimal(0)  # weight of items seen

    def add(self, x, w=1):
        "add another datapoint to the Mean / Variance / Standard Deviation"
        if not isinstance(x, Decimal):
            x = Decimal(x)
        if not self.is_started:
            self.m = x
            self.ss = Decimal(0)
            self.total_w = w
            self.is_started = True
        else:
            temp_w = self.total_w + w
            self.ss += (self.total_w * w * (x - self.m) *
                        (x - self.m)) / temp_w
            self.m += (x - self.m) / temp_w
            self.total_w = temp_w

    def var(self):
        return self.ss / self.total_w

    def sd(self):
        return math.sqrt(self.var())

    def mean(self):
        return self.m

DataPoint = namedtuple('DataPoint', ['value', 'count'])

def test_mvsd():
    mvsd = MVSD()
    for x in range(10):
        mvsd.add(x)

    assert '%.2f' % mvsd.mean() == "4.50"
    assert '%.2f' % mvsd.var() == "8.25"
    assert '%.14f' % mvsd.sd() == "2.87228132326901"

def median(values, key=None):
    if not key:
        key = None  # map and sort accept None as identity
    length = len(values)
    if length % 2:
        median_indeces = [length//2]
    else:
        median_indeces = [length//2-1, length//2]

    values = sorted(values, key=key)
    return sum(map(key,
                   [values[i] for i in median_indeces])) / len(median_indeces)


def test_median():
    assert 6 == median([8, 7, 9, 1, 2, 6, 3])  # odd-sized list
    assert 4 == median([4, 5, 2, 1, 9, 10])  # even-sized int list. (4+5)/2 = 4
    # even-sized float list. (4.0+5)/2 = 4.5
    assert "4.50" == "%.2f" % median([4.0, 5, 2, 1, 9, 10])


def histogram(stream, options):
    """
    Loop over the stream and add each entry to the dataset, printing out at the
    end.

    stream yields Decimal()
    """
    if not options.min or not options.max:
        # glob the iterator here so we can do min/max on it
        data = list(stream)
    else:
        data = stream
    bucket_scale = 1

    if options.min:
        min_v = Decimal(options.min)
    else:
        min_v = min(data, key=lambda x: x.value)
        min_v = min_v.value
    if options.max:
        max_v = Decimal(options.max)
    else:
        max_v = max(data, key=lambda x: x.value)
        max_v = max_v.value

    if not max_v > min_v:
        raise ValueError('max must be > min. max:%s min:%s' % (max_v, min_v))
    diff = max_v - min_v

    boundaries = []
    bucket_counts = []
    buckets = 0

    if options.custom_bins:
        bound = options.custom_bins.split(',')
        bound_sort = sorted(map(Decimal, bound))

        # if the last value is smaller than the maximum, replace it
        if bound_sort[-1] < max_v:
            bound_sort[-1] = max_v

        # iterate through the sorted list and append to boundaries
        for x in bound_sort:
            if x >= min_v and x <= max_v:
                boundaries.append(x)
            elif x >= max_v:
                boundaries.append(max_v)
                break

        # beware: the min_v is not included in the boundaries,
        # so no need to do a -1!
        bucket_counts = [0 for x in range(len(boundaries))]
        buckets = len(boundaries)
    elif options.logscale:
        buckets = options.bins and int(options.bins) or 10
        if buckets <= 0:
            raise ValueError('# of buckets must be > 0')

        def first_bucket_size(k, n):
            # Logarithmic buckets means, the size of bucket i+1 is twice
            # the size of bucket i.
            # For k+1 buckets whose sum is n, we have
            # (note, k+1 buckets, since 0 is counted as well):
            #     \sum_{i=0}^{k} x*2^i   = n
            #     x * \sum_{i=0}^{k} 2^i = n
            #     x * (2^{k+1} - 1)      = n
            #     x = n/(2^{k+1} - 1)
            
            return n/(2**(k+1)-1)

        def log_steps(k, n):
            "k logarithmic steps whose sum is n"
            x = first_bucket_size(k-1, n)
            sum = 0
            for i in range(k):
                sum += 2**i * x
                yield sum
        bucket_counts = [0 for x in range(buckets)]
        for step in log_steps(buckets, diff):
            boundaries.append(min_v + step)
    else:
        buckets = options.bins and int(options.bins) or 10
        if buckets <= 0:
            raise ValueError('# of buckets must be > 0')
        step = diff / buckets
        bucket_counts = [0 for x in range(buckets)]
        for x in range(buckets):
            boundaries.append(min_v + (step * (x + 1)))

    skipped = 0
    samples = 0
    mvsd = MVSD()
    accepted_data = []
    for record in data:
        samples += record.count
        if options.no_mvsd:
            mvsd.add(record.value, record.count)
            accepted_data.append(record)
        # find the bucket this goes in
        if record.value < min_v or record.value > max_v:
            skipped += record.count
            continue
        for bucket_postion, boundary in enumerate(boundaries):
            if record.value <= boundary:
                bucket_counts[bucket_postion] += record.count
                break

    # auto-pick the hash scale
    if max(bucket_counts) > 75:
        bucket_scale = int(max(bucket_counts) / 75)

    print(("# NumSamples = %d; Min = %0.2f; Max = %0.2f" %
          (samples, min_v, max_v)))
    if skipped:
        print(("# %d value%s outside of min/max" %
              (skipped, skipped > 1 and 's' or '')))
    if options.no_mvsd:
        print(("# Mean = %f; Variance = %f; SD = %f; Median %f" %
              (mvsd.mean(), mvsd.var(), mvsd.sd(),
               median(accepted_data, key=lambda x: x.value))))
    print("# each " + options.dot + " represents a count of %d" % bucket_scale)
    bucket_min = min_v
    bucket_max = min_v
    percentage = ""
    format_string = options.bin_format + ' - ' + options.bin_format + ' [%6d]: %s%s'
    for bucket in range(buckets):
        bucket_min = bucket_max
        bucket_max = boundaries[bucket]
        bucket_count = bucket_counts[bucket]
        star_count = 0
        if bucket_count:
            star_count = bucket_count // bucket_scale
        if options.percentage:
            percentage = " (%0.2f%%)" % (100 * Decimal(bucket_count) /
                                         Decimal(samples))
        print(format_string % (bucket_min, bucket_max, bucket_count, options.dot *
                               star_count, percentage))
