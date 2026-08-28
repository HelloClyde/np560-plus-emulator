import unittest

import patch_np560_mask_rom_resource as resource


class MaskRomResourcePatchTests(unittest.TestCase):
    def test_flag_and_path_follow_external_byte_lane(self) -> None:
        image = bytes([0xCC]) * resource.LOGICAL_END
        patched, encoded = resource.patch_image(image, r"0:\lirt.nwf", "ascii")

        # Logical byte A is stored at backing byte A^1.
        self.assertEqual(
            patched[resource.RESOURCE_FLAG_ADDRESS ^ 1], 1
        )
        for index, value in enumerate(encoded + b"\0"):
            self.assertEqual(
                patched[(resource.RESOURCE_PATH_ADDRESS + index) ^ 1], value
            )
        self.assertEqual(
            patched[resource.RESOURCE_PATH_ADDRESS + len(encoded) + 1], 0
        )

    def test_rejects_path_without_room_for_nul(self) -> None:
        image = bytes(resource.LOGICAL_END)
        with self.assertRaises(ValueError):
            resource.patch_image(
                image, "x" * resource.RESOURCE_PATH_SIZE, "ascii"
            )


if __name__ == "__main__":
    unittest.main()
