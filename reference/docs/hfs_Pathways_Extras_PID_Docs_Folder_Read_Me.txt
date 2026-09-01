Here are some documents I've prepared relating to Bungie's game Pathways into Darkness:

PIDMapReader.h -- C++ header file for reading in the map file. It contains the level format as the object PID_Level and its subobjects.

PIDMapReader.cp -- Code for reading in the level.

SimpleVec.h -- a utility class for arrays with automatic deallocation.

sector_types_sqr.gif -- map of all the levels, showing their sector types.

Update (April 5, 2000):

PIDMapReader.h:

Corrected wall/corner types.

Added Ben Semmler's monster identifications and identification of Unknown2, corrected for monster-name/death-message order in PID app.

Identified Unknown1's last 16 bytes as a set of 8 shorts for texture ID's.