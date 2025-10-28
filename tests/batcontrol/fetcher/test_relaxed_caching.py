"""Unit tests for fetcher.relaxed_caching module"""

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
        assert cache.ttl_seconds == 12 * 3600  # 12 hours in seconds
        assert cache.max_entries == 2

    def test_store_and_get(self):
        """Test basic store and retrieve"""
        cache = RelaxedCaching()
        test_data = {'key': 'value', 'number': 42}

        cache.store_new_entry(test_data)
        retrieved = cache.get_last_entry()

        assert retrieved == test_data

    def test_cache_miss_empty(self):
        """Test CacheMissError when cache is empty"""
        cache = RelaxedCaching()

        with pytest.raises(CacheMissError):
            cache.get_last_entry()

    def test_cache_expiration(self):
        """Test cache expiration after TTL"""
        cache = RelaxedCaching(ttl_hours=0.001)  # ~3.6 seconds
        cache.store_new_entry({'data': 'test'})

        time.sleep(4)

        with pytest.raises(CacheMissError):
            cache.get_last_entry()

    def test_max_entries_limit(self):
        """Test that cache respects max_entries limit"""
        cache = RelaxedCaching(max_entries=3)

        for i in range(4):
            cache.store_new_entry({'entry': i})
            time.sleep(0.01)

        assert len(cache.cache_store) == 3
        assert cache.get_last_entry() == {'entry': 3}

    def test_thread_safety(self):
        """Test thread safety with concurrent operations"""
        cache = RelaxedCaching()
        results = []

        def worker(thread_id):
            cache.store_new_entry({'thread': thread_id})
            try:
                data = cache.get_last_entry()
                results.append(data)
            except CacheMissError:
                pass

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have succeeded without errors
        assert len(cache.cache_store) <= cache.max_entries
