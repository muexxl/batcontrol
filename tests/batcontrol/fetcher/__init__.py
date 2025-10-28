"""Unit tests for RelaxedCaching module in fetcher package"""

import time
import threading
import pytest
from batcontrol.fetcher import RelaxedCaching, CacheMissError


class TestRelaxedCaching:
    """Test suite for RelaxedCaching class"""

    def test_initialization(self):
        """Test that RelaxedCaching initializes correctly"""
        cache = RelaxedCaching()
        assert cache.entry_key is None
        assert cache.cache_store == {}
        assert cache.ttl_seconds == 18 * 3600  # 18 hours in seconds
        assert cache.max_entries == 3

    def test_initialization_custom_ttl(self):
        """Test initialization with custom TTL"""
        cache = RelaxedCaching(ttl_hours=6.0)
        assert cache.ttl_seconds == 6 * 3600

    def test_initialization_custom_max_entries(self):
        """Test initialization with custom max_entries"""
        cache = RelaxedCaching(max_entries=5)
        assert cache.max_entries == 5

    def test_store_new_entry(self):
        """Test storing a new entry"""
        cache = RelaxedCaching()
        test_data = {'key': 'value', 'number': 42}

        timestamp = cache.store_new_entry(test_data)

        assert cache.entry_key == timestamp
        assert timestamp in cache.cache_store
        assert cache.cache_store[timestamp] == test_data
        assert len(cache.cache_store) == 1

    def test_get_last_entry_success(self):
        """Test retrieving the last entry successfully"""
        cache = RelaxedCaching()
        test_data = {'forecast': [1, 2, 3, 4]}

        cache.store_new_entry(test_data)
        retrieved_data = cache.get_last_entry()

        assert retrieved_data == test_data

    def test_get_last_entry_cache_miss_empty(self):
        """Test that get_last_entry raises CacheMissError when cache is empty"""
        cache = RelaxedCaching()

        with pytest.raises(CacheMissError) as exc_info:
            cache.get_last_entry()

        assert 'entry_key is None' in str(exc_info.value)

    def test_get_last_entry_cache_expired(self):
        """Test that get_last_entry raises CacheMissError when entry is expired"""
        cache = RelaxedCaching(ttl_hours=0.001)  # Very short TTL for testing (3.6 seconds)
        test_data = {'data': 'test'}

        cache.store_new_entry(test_data)
        time.sleep(4)  # Wait for expiration

        with pytest.raises(CacheMissError) as exc_info:
            cache.get_last_entry()

        assert 'expired' in str(exc_info.value)

    def test_multiple_entries(self):
        """Test storing multiple entries"""
        cache = RelaxedCaching()

        data1 = {'entry': 1}
        data2 = {'entry': 2}
        data3 = {'entry': 3}

        timestamp1 = cache.store_new_entry(data1)
        time.sleep(0.01)  # Ensure different timestamps
        timestamp2 = cache.store_new_entry(data2)
        time.sleep(0.01)
        timestamp3 = cache.store_new_entry(data3)

        # Should have 3 entries
        assert len(cache.cache_store) == 3

        # Last entry should be data3
        assert cache.get_last_entry() == data3
        assert cache.entry_key == timestamp3

        # All entries should be in cache
        assert timestamp1 in cache.cache_store
        assert timestamp2 in cache.cache_store
        assert timestamp3 in cache.cache_store

    def test_max_entries_limit(self):
        """Test that cache respects max_entries limit"""
        cache = RelaxedCaching(max_entries=3)

        # Store 4 entries
        for i in range(4):
            cache.store_new_entry({'entry': i})
            time.sleep(0.01)  # Ensure different timestamps

        # Should only have 3 entries (oldest removed)
        assert len(cache.cache_store) == 3

        # The current entry_key should point to the last entry
        assert cache.get_last_entry() == {'entry': 3}

    def test_clear_cache(self):
        """Test clearing the cache"""
        cache = RelaxedCaching()

        cache.store_new_entry({'data': 'test1'})
        cache.store_new_entry({'data': 'test2'})

        assert len(cache.cache_store) == 2
        assert cache.entry_key is not None

        cache.clear_cache()

        assert len(cache.cache_store) == 0
        assert cache.entry_key is None

    def test_get_cache_info_empty(self):
        """Test get_cache_info on empty cache"""
        cache = RelaxedCaching()

        info = cache.get_cache_info()

        assert info['entry_count'] == 0
        assert info['entry_key'] is None
        assert info['oldest_entry'] is None
        assert info['newest_entry'] is None
        assert info['cache_age_seconds'] is None

    def test_get_cache_info_with_entries(self):
        """Test get_cache_info with entries"""
        cache = RelaxedCaching()

        cache.store_new_entry({'data': 'test1'})
        time.sleep(0.01)
        cache.store_new_entry({'data': 'test2'})

        info = cache.get_cache_info()

        assert info['entry_count'] == 2
        assert info['entry_key'] is not None
        assert info['oldest_entry'] is not None
        assert info['newest_entry'] is not None
        assert info['cache_age_seconds'] is not None
        assert info['cache_age_seconds'] >= 0
        assert info['oldest_entry'] < info['newest_entry']

    def test_thread_safety_concurrent_stores(self):
        """Test thread safety with concurrent store operations"""
        cache = RelaxedCaching()
        results = []

        def store_data(thread_id):
            timestamp = cache.store_new_entry({'thread': thread_id})
            results.append(timestamp)

        threads = []
        for i in range(10):
            t = threading.Thread(target=store_data, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All stores should have succeeded
        assert len(results) == 10

        # Cache should contain at most max_entries
        assert len(cache.cache_store) <= cache.max_entries

        # entry_key should be one of the stored timestamps
        assert cache.entry_key in results

    def test_thread_safety_concurrent_reads(self):
        """Test thread safety with concurrent read operations"""
        cache = RelaxedCaching()
        cache.store_new_entry({'data': 'test_data'})

        results = []
        errors = []

        def read_data():
            try:
                data = cache.get_last_entry()
                results.append(data)
            except CacheMissError as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=read_data)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All reads should have succeeded
        assert len(results) == 10
        assert len(errors) == 0
        assert all(r == {'data': 'test_data'} for r in results)

    def test_thread_safety_mixed_operations(self):
        """Test thread safety with mixed read/write operations"""
        cache = RelaxedCaching(max_entries=5)
        cache.store_new_entry({'initial': 'data'})

        def worker(worker_id):
            for i in range(5):
                if i % 2 == 0:
                    cache.store_new_entry({'worker': worker_id, 'iteration': i})
                else:
                    try:
                        cache.get_last_entry()
                    except CacheMissError:
                        pass  # Can happen during concurrent operations
                time.sleep(0.001)

        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Cache should be valid after all operations
        assert cache.entry_key is not None
        assert len(cache.cache_store) <= cache.max_entries

        # Should be able to retrieve last entry
        last_entry = cache.get_last_entry()
        assert isinstance(last_entry, dict)

    def test_store_complex_data_structures(self):
        """Test storing complex data structures"""
        cache = RelaxedCaching()

        complex_data = {
            'prices': {0: 10.5, 1: 12.3, 2: 8.7},
            'metadata': {
                'provider': 'test',
                'timestamp': time.time(),
                'nested': {'key': 'value'}
            },
            'list_data': [1, 2, 3, 4, 5]
        }

        cache.store_new_entry(complex_data)
        retrieved = cache.get_last_entry()

        assert retrieved == complex_data
        assert retrieved['prices'][1] == 12.3
        assert retrieved['metadata']['nested']['key'] == 'value'
