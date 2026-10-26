from collections import deque
import unittest
from unittest.mock import patch

from app.shared import observability


class ObservabilityTest(unittest.TestCase):
    def test_bounded_redacted_ring_and_newest_first(self):
        with patch.object(observability, "_events", deque(maxlen=500)):
            for index in range(501):
                observability.record_request(str(index), "GET",
                    "/api/v1/meals/private-id?token=secret", 200, 0.25)
            result = observability.recent_requests(2)
        self.assertEqual(result["retained"], 500)
        self.assertEqual([event["request_id"] for event in result["events"]], ["500", "499"])
        self.assertEqual(result["events"][0]["module"], "nutrition")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("private-id", str(result))


if __name__ == "__main__":
    unittest.main()
