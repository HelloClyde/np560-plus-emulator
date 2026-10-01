"""World movement must not be confused with screen position or scrolling."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_np560_eq_web_bundle import scene_position


class SceneCoordinates(unittest.TestCase):
    def status(self, y=2, offset=11):
        return dict(current_x=7, current_y=y, current_offset_x=1,
                    current_offset_y=offset, current_map_index=1, current_direction=2)

    def test_scroll_is_real_world_movement(self):
        before = scene_position(self.status())
        after = scene_position(self.status(offset=10))
        self.assertEqual(before['current_y'], after['current_y'])
        self.assertEqual((before['world_x'], before['world_y']), (8, 13))
        self.assertEqual((after['world_x'], after['world_y']), (8, 12))

    def test_changed_screen_does_not_imply_movement(self):
        before = scene_position(self.status(y=1, offset=11))
        after = scene_position(self.status(y=2, offset=10))
        self.assertEqual(before['world_y'], after['world_y'])
        self.assertNotEqual(before['current_y'], after['current_y'])

    def test_missing_viewport_is_not_zero(self):
        status = self.status()
        del status['current_offset_y']
        with self.assertRaises(KeyError):
            scene_position(status)


if __name__ == '__main__':
    unittest.main()
