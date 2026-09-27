import unittest

from automation.posters.tiktok_poster import TikTokPoster


class _Locator:
    @property
    def first(self):
        return self

    async def is_visible(self, timeout=None):
        return True

    async def click(self, force=False):
        return None


class _Page:
    def __init__(self):
        self.scripts = []

    def locator(self, selector):
        return _Locator()

    async def evaluate(self, script, arg=None):
        self.scripts.append(script)
        return True


class _PickerPoster(TikTokPoster):
    def __init__(self, matches):
        super().__init__()
        self.matches = iter(matches)
        self.time_attempts = 0
        self.date_attempts = 0

    async def _set_time_picker(self, page, native):
        self.time_attempts += 1
        return True

    async def _set_date_picker(self, page, native):
        self.date_attempts += 1
        return True

    async def _dismiss_schedule_pickers(self, page):
        return None

    async def _picker_shows_time(self, page, native):
        return next(self.matches)


class TikTokTimePickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_clicks_exact_hour_and_minute_text_not_wheel_container(self):
        page = _Page()
        poster = TikTokPoster()

        self.assertTrue(
            await poster._set_time_picker(page, {"hour": 11, "minute": 30})
        )
        scripts = "\n".join(page.scripts)
        self.assertIn("hit.click()", scripts)
        self.assertNotIn("closest('.tiktok-timepicker-option-item')", scripts)

    async def test_retries_once_then_accepts_exact_time(self):
        poster = _PickerPoster([False, True])

        self.assertTrue(
            await poster._configure_schedule_picker(
                object(), {"time": "11:30", "label": "28/09/2026 11:30"}
            )
        )
        self.assertEqual(poster.time_attempts, 2)
        self.assertEqual(poster.date_attempts, 1)

    async def test_fails_closed_when_time_still_mismatches(self):
        poster = _PickerPoster([False, False])

        self.assertFalse(
            await poster._configure_schedule_picker(
                object(), {"time": "11:30", "label": "28/09/2026 11:30"}
            )
        )
        self.assertEqual(poster.time_attempts, 2)


if __name__ == "__main__":
    unittest.main()
