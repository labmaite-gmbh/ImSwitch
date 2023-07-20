from .PositionerManager import PositionerManager


class MockPositionerManager(PositionerManager):
    """ PositionerManager for mock positioner used for repeating measurements and/or timelapses.

    Manager properties:

    None
    """

    def __init__(self, positionerInfo, name, **lowLevelManagers):

        # if len(positionerInfo.axes) != 1:
        #     raise RuntimeError(f'{self.__class__.__name__} only supports one axis,'
        #                        f' {len(positionerInfo.axes)} provided.')
                               
        super().__init__(positionerInfo, name, initialPosition={
            axis: 0 for axis in positionerInfo.axes
        },)

    def move(self, value, axis, is_blocking = False, is_absolute = False, speed = [10,10,10]):
        if isinstance(value, list) or isinstance(value, tuple):
            if is_absolute:
                [self.setPosition(v, a) for a,v in zip(axis, value)]
            else:
                [self.setPosition(self._position[a] + v, a) for a,v in zip(axis, value)]
        else:
            if is_absolute:
                self.setPosition(value, axis)
            else:
                self.setPosition(self._position[axis] + value, axis)

    def setPosition(self, position, axis):
        if isinstance(position, list) or isinstance(position, tuple):
            for a, p in zip(axis, position):
                self._position[a] = p
        else:
            self._position[axis] = position

    def get_position(self):
        return [p for p in self._position.values()]

    def doHome(self, axis):
        print(f"Homing {axis}...")

    def forceStop(self, axis):
        print(f"Stopping {axis}")

# Copyright (C) 2020-2021 ImSwitch developers
# This file is part of ImSwitch.
#
# ImSwitch is free software: you can revalueribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ImSwitch is valueributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
