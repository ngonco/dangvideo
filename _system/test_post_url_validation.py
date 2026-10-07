import sys
import unittest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from automation.posters.facebook_poster import FacebookPoster
from automation.posters.tiktok_poster import TikTokPoster


class PostUrlValidationTests(unittest.TestCase):
    def test_tiktok_accepts_only_video_permalink(self):
        poster = TikTokPoster()
        self.assertTrue(poster._is_tt_permalink("https://www.tiktok.com/@hocgoihocmo26/video/7689655714016398599"))
        self.assertFalse(poster._is_tt_permalink("https://www.tiktok.com/@hocgoihocmo26"))
        self.assertFalse(poster._is_tt_permalink("https://www.tiktok.com/tiktokstudio/content"))

    def test_facebook_rejects_page_and_library_urls(self):
        poster = FacebookPoster()
        self.assertTrue(poster._is_fb_permalink("https://www.facebook.com/share/r/1HpHVHLMuH/"))
        self.assertTrue(poster._is_fb_permalink("https://www.facebook.com/reel/123456789"))
        self.assertFalse(poster._is_fb_permalink("https://www.facebook.com/hocgoihocmo26/"))
        self.assertFalse(poster._is_fb_permalink(
            "https://www.facebook.com/professional_dashboard/content/content_library/"
        ))
        self.assertEqual(
            poster._normalize_fb_permalink(
                "https://www.facebook.com/reel/1113793974848599/?notif_id=123&ref=notif"
            ),
            "https://www.facebook.com/reel/1113793974848599/",
        )

    def test_facebook_accepts_video_share_links_and_removes_tracking(self):
        poster = FacebookPoster()
        for path in ('share/r/1HpHVHLMuH/', 'share/v/NEWVIDEO123/'):
            self.assertTrue(poster._is_fb_permalink('https://www.facebook.com/'+path+'?mibextid=TEST'))
            self.assertEqual(poster._normalize_fb_permalink('https://www.facebook.com/'+path+'?mibextid=TEST'),
                             'https://www.facebook.com/'+path)
        for url in ('https://facebook.com.evil.example/share/v/123/',
                    'https://evil.example/facebook.com/share/v/123/',
                    'https://www.facebook.com/share/v/',
                    'https://www.facebook.com/share/v/abc/another/path'):
            self.assertFalse(poster._is_fb_permalink(url))


if __name__ == "__main__":
    unittest.main()
