# Generated parsers

Rebuild from `formats/pid_level.ksy` with kaitai-struct-compiler 0.11:

```
kaitai-struct-compiler formats/pid_level.ksy -t python --outdir tools/generated
kaitai-struct-compiler formats/pid_level.ksy -t csharp --dotnet-namespace Pid.Formats --outdir tools/generated
```

- `pid_maps.py` — Python (needs `kaitaistruct>=0.11`)
- `PidMaps.cs` — C# for Unity (needs NuGet `KaitaiStruct.Runtime.CSharp`)

The hand-written `tools/pid_level.py` is the project parser. These files are the
machine-generated counterpart of the same layout.
