/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

import { describe, it, expect } from "vitest"
import {
  bytesAreEqual,
  zeros,
  arrayToBytes,
  BufferReader,
  BufferWriter,
  utf8ToBytes,
  bytesToUtf8,
  bytesToHex,
} from "../utils"
import { TLSError } from "../alerts"

describe("bytesAreEqual", () => {
  it("returns true for a variety of equal byte arrays", () => {
    expect(bytesAreEqual(zeros(0), zeros(0))).toBe(true)
    expect(bytesAreEqual(zeros(7), zeros(7))).toBe(true)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3]), arrayToBytes([1, 2, 3]))
    ).toBe(true)
  })

  it("returns false for a variety of non-equal byte arrays", () => {
    expect(bytesAreEqual(zeros(0), zeros(1))).toBe(false)
    expect(bytesAreEqual(zeros(1), zeros(0))).toBe(false)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3]), arrayToBytes([2, 2, 3]))
    ).toBe(false)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3]), arrayToBytes([1, 1, 3]))
    ).toBe(false)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3]), arrayToBytes([1, 2, 4]))
    ).toBe(false)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3]), arrayToBytes([1, 2, 3, 4]))
    ).toBe(false)
    expect(
      bytesAreEqual(arrayToBytes([1, 2, 3, 4]), arrayToBytes([1, 2, 3]))
    ).toBe(false)
  })

  it("throws on a variety of bad inputs", () => {
    expect(() => bytesAreEqual(0 as unknown as Uint8Array, 0 as unknown as Uint8Array)).toThrow()
    expect(() => bytesAreEqual(null as unknown as Uint8Array, 0 as unknown as Uint8Array)).toThrow()
    expect(() =>
      bytesAreEqual(
        { some: "object" } as unknown as Uint8Array,
        { another: "object" } as unknown as Uint8Array
      )
    ).toThrow()
  })
})

describe("the BufferReader class", () => {
  it("handles basic reading and seeking correctly", () => {
    const buf = new BufferReader(utf8ToBytes("hello world"))
    expect(buf.length()).toBe(11)
    expect(buf.tell()).toBe(0)
    expect(bytesToUtf8(buf.readBytes(5))).toBe("hello")
    expect(buf.hasMoreBytes()).toBe(true)
    expect(buf.tell()).toBe(5)
    buf.incr(2)
    expect(buf.tell()).toBe(7)
    expect(buf.hasMoreBytes()).toBe(true)
    expect(bytesToUtf8(buf.readBytes(4))).toBe("orld")
    expect(buf.hasMoreBytes()).toBe(false)
    buf.seek(2)
    expect(buf.tell()).toBe(2)
    expect(bytesToUtf8(buf.readBytes(5))).toBe("llo w")
  })

  it("errors if attempting to seek beyond the start of the buffer", () => {
    const buf = new BufferReader(utf8ToBytes("hello world"))
    expect(() => {
      buf.seek(-1)
    }).toThrow(TLSError)
    expect(buf.tell()).toBe(0)
  })

  it("errors if attempting to seek beyond the end of the buffer", () => {
    const buf = new BufferReader(utf8ToBytes("hello world"))
    expect(() => {
      buf.seek(12)
    }).toThrow(TLSError)
    expect(buf.tell()).toBe(0)
  })

  it("errors if attempting to read beyond the end of the buffer", () => {
    const buf = new BufferReader(utf8ToBytes("hello world"))
    buf.seek(2)
    expect(() => {
      buf.readBytes(12)
    }).toThrow(TLSError)
    expect(buf.tell()).toBe(2)
  })

  it("correctly reads integer primitives at various offsets", () => {
    const buf = new BufferReader(arrayToBytes([132, 42, 17, 4, 0]))
    expect(buf.readUint8()).toBe(132)
    expect(buf.tell()).toBe(1)
    expect(buf.readUint8()).toBe(42)
    expect(buf.tell()).toBe(2)
    expect(buf.readUint8()).toBe(17)
    expect(buf.tell()).toBe(3)
    expect(buf.readUint8()).toBe(4)
    expect(buf.tell()).toBe(4)
    expect(buf.readUint8()).toBe(0)
    expect(buf.tell()).toBe(5)

    buf.seek(0)
    buf.seek(0)
    expect(buf.readUint16()).toBe(33834)
    expect(buf.tell()).toBe(2)
    buf.incr(-1)
    expect(buf.readUint16()).toBe(10769)
    expect(buf.tell()).toBe(3)
    expect(buf.readUint16()).toBe(1024)
    expect(buf.tell()).toBe(5)

    buf.seek(0)
    expect(buf.readUint24()).toBe(8661521)
    expect(buf.tell()).toBe(3)
    buf.seek(1)
    expect(buf.readUint24()).toBe(2756868)
    expect(buf.tell()).toBe(4)

    buf.seek(0)
    expect(buf.readUint32()).toBe(2217349380)
    expect(buf.tell()).toBe(4)
    buf.seek(1)
    expect(buf.readUint32()).toBe(705758208)
    expect(buf.tell()).toBe(5)
  })

  it("errors if reading integer primitives past the end of the buffer", () => {
    const buf = new BufferReader(arrayToBytes([132, 42, 17, 4, 1]))
    buf.seek(5)
    expect(() => buf.readUint8()).toThrow(TLSError)
    buf.seek(5)
    expect(() => buf.readUint16()).toThrow(TLSError)
    buf.seek(5)
    expect(() => buf.readUint24()).toThrow(TLSError)
    buf.seek(5)
    expect(() => buf.readUint32()).toThrow(TLSError)

    buf.seek(4)
    expect(buf.readUint8()).toBeTruthy()
    buf.seek(4)
    expect(() => buf.readUint16()).toThrow(TLSError)
    buf.seek(4)
    expect(() => buf.readUint24()).toThrow(TLSError)
    buf.seek(4)
    expect(() => buf.readUint32()).toThrow(TLSError)

    buf.seek(3)
    expect(buf.readUint8()).toBeTruthy()
    buf.seek(3)
    expect(buf.readUint16()).toBeTruthy()
    buf.seek(3)
    expect(() => buf.readUint24()).toThrow(TLSError)
    buf.seek(3)
    expect(() => buf.readUint32()).toThrow(TLSError)

    buf.seek(2)
    expect(buf.readUint8()).toBeTruthy()
    buf.seek(2)
    expect(buf.readUint16()).toBeTruthy()
    buf.seek(2)
    expect(buf.readUint24()).toBeTruthy()
    buf.seek(2)
    expect(() => buf.readUint32()).toThrow(TLSError)
  })

  it("correctly reads variable-length vectors of bytes", () => {
    let buf = new BufferReader(arrayToBytes([4, 1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.readVectorBytes8(), arrayToBytes([1, 2, 3, 4]))
    ).toBe(true)
    expect(buf.tell()).toBe(5)
    buf = new BufferReader(arrayToBytes([0, 0, 0]))
    expect(bytesAreEqual(buf.readVectorBytes8(), arrayToBytes([]))).toBe(true)
    expect(buf.tell()).toBe(1)

    buf = new BufferReader(arrayToBytes([0, 4, 1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.readVectorBytes16(), arrayToBytes([1, 2, 3, 4]))
    ).toBe(true)
    expect(buf.tell()).toBe(6)

    buf = new BufferReader(arrayToBytes([0, 0, 4, 1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.readVectorBytes24(), arrayToBytes([1, 2, 3, 4]))
    ).toBe(true)
    expect(buf.tell()).toBe(7)
  })

  it("correctly reads variable-length vectors using a callback", () => {
    let readValues: number[] = []
    let buf = new BufferReader(arrayToBytes([42, 4, 1, 2, 3, 4, 5]))
    buf.seek(1)
    buf.readVector8((contentsBuf, n) => {
      expect(contentsBuf.length()).toBe(4)
      expect(n).toBe(readValues.length)
      readValues.push(contentsBuf.readUint8())
    })
    expect(readValues).toEqual([1, 2, 3, 4])
    expect(buf.tell()).toBe(6)

    readValues = []
    buf = new BufferReader(arrayToBytes([42, 0, 4, 1, 2, 3, 4, 5]))
    buf.seek(1)
    buf.readVector16((contentsBuf, n) => {
      expect(contentsBuf.length()).toBe(4)
      expect(n).toBe(readValues.length)
      readValues.push(contentsBuf.readUint16())
    })
    expect(readValues).toEqual([(1 << 8) | 2, (3 << 8) | 4])
    expect(buf.tell()).toBe(7)

    readValues = []
    buf = new BufferReader(arrayToBytes([42, 0, 0, 4, 1, 2, 3, 4, 5]))
    buf.seek(1)
    buf.readVector24((contentsBuf, n) => {
      expect(contentsBuf.length()).toBe(4)
      expect(n).toBe(readValues.length)
      readValues.push(contentsBuf.readUint8())
    })
    expect(readValues).toEqual([1, 2, 3, 4])
    expect(buf.tell()).toBe(8)
  })

  it("errors if a vector read consumes too many bytes", () => {
    const buf = new BufferReader(arrayToBytes([2, 1, 2, 3]))
    expect(() => {
      buf.readVector8((contentsBuf) => {
        expect(contentsBuf.length()).toBe(2)
        contentsBuf.readUint24()
      })
    }).toThrow(TLSError)
  })

  it("errors if a vector read somehow consumes too few bytes", () => {
    const buf = new BufferReader(arrayToBytes([3, 1, 2, 3]))
    expect(() => {
      buf.readVector8((contentsBuf) => {
        expect(contentsBuf.length()).toBe(3)
        expect(contentsBuf.readUint8()).toBe(1)
        expect(contentsBuf.readUint8()).toBe(2)
        expect(contentsBuf.readUint8()).toBe(3)
        // simulate some bug that changes the underlying buffer.
        buf.incr(-1)
      })
    }).toThrow(TLSError)
  })

  it("errors if a vector read consumes no bytes", () => {
    const buf = new BufferReader(arrayToBytes([3, 1, 2, 3]))
    expect(() => {
      buf.readVector8((contentsBuf) => {
        expect(contentsBuf.length()).toBe(3)
        // don't consume anything, risking an infinite loop.
      })
    }).toThrow(TLSError)
  })

  it("errors if a nested vector read would exceed the outer buffer length", () => {
    // A vector of length 5, inside a vector of length 3.
    const buf = new BufferReader(arrayToBytes([3, 5, 1, 2, 3, 4, 5]))
    expect(() => {
      buf.readVector8((contentsBuf) => {
        expect(contentsBuf.length()).toBe(3)
        contentsBuf.readVector8(() => {
          expect.fail("the callback should not get called")
        })
      })
    }).toThrow(TLSError)
  })
})

describe("the BufferWriter class", () => {
  it("grows appropriately as data is written", () => {
    const buf = new BufferWriter(2)
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    expect(buf.tell()).toBe(5)
    expect(buf.length()).toBe(6)
  })

  it("can read back written data using `slice`", () => {
    const buf = new BufferWriter(2)
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    expect(buf.tell()).toBe(5)
    expect(bytesAreEqual(buf.slice(), arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
    expect(buf.tell()).toBe(5)
    expect(bytesAreEqual(buf.slice(1), arrayToBytes([2, 3, 4, 5]))).toBe(true)
    expect(buf.tell()).toBe(5)
    expect(bytesAreEqual(buf.slice(1, 3), arrayToBytes([2, 3]))).toBe(true)
    expect(buf.tell()).toBe(5)
    expect(bytesAreEqual(buf.slice(1, -1), arrayToBytes([2, 3, 4]))).toBe(true)
    expect(buf.tell()).toBe(5)
  })

  it("refuses to slice past the start of the buffer", () => {
    const buf = new BufferWriter(2)
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    expect(() => buf.slice(-1)).toThrow(TLSError)
    expect(() => buf.slice(0, -50)).toThrow(TLSError)
  })

  it("refuses to slice past the end of the buffer", () => {
    const buf = new BufferWriter(2)
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    expect(() => buf.slice(2, 50)).toThrow(TLSError)
  })

  it("returns and resets the buffer on flush", () => {
    const buf = new BufferWriter()
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    expect(bytesAreEqual(buf.flush(), arrayToBytes([1, 2, 3, 4, 5]))).toBe(true)
    expect(buf.tell()).toBe(0)
    expect(bytesAreEqual(buf.slice(), arrayToBytes([]))).toBe(true)
  })

  it("truncates at the current position on flush", () => {
    const buf = new BufferWriter()
    buf.writeBytes(arrayToBytes([1, 2, 3, 4, 5]))
    buf.incr(-2)
    expect(bytesAreEqual(buf.flush(), arrayToBytes([1, 2, 3]))).toBe(true)
    expect(buf.tell()).toBe(0)
  })

  it("correctly writes integer primitives at various offsets", () => {
    const buf = new BufferWriter()
    for (let i = 0; i < 10; i++) {
      buf.writeUint8(i)
    }
    expect(buf.tell()).toBe(10)
    expect(
      bytesAreEqual(
        buf.flush(),
        arrayToBytes([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
      )
    ).toBe(true)

    for (let i = 0; i < 9; i++) {
      buf.writeUint16(i)
    }
    buf.writeUint16(3079)
    expect(buf.tell()).toBe(20)
    expect(
      bytesAreEqual(
        buf.flush(),
        arrayToBytes([
          0, 0, 0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0, 8, 12, 7,
        ])
      )
    ).toBe(true)

    for (let i = 0; i < 5; i++) {
      buf.writeUint24(i)
    }
    buf.writeUint24(788229)
    expect(buf.tell()).toBe(18)
    expect(
      bytesAreEqual(
        buf.flush(),
        arrayToBytes([
          0, 0, 0, 0, 0, 1, 0, 0, 2, 0, 0, 3, 0, 0, 4, 12, 7, 5,
        ])
      )
    ).toBe(true)

    for (let i = 0; i < 5; i++) {
      buf.writeUint32(i)
    }
    buf.writeUint32(201786627)
    expect(buf.tell()).toBe(24)
    expect(
      bytesAreEqual(
        buf.flush(),
        arrayToBytes([
          0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 4, 12,
          7, 5, 3,
        ])
      )
    ).toBe(true)

    buf.writeUint8(1)
    buf.writeUint16(2)
    buf.writeUint24(3)
    buf.writeUint8(4)
    buf.writeUint32(5)
    expect(
      bytesAreEqual(
        buf.flush(),
        arrayToBytes([1, 0, 2, 0, 0, 3, 4, 0, 0, 0, 5])
      )
    ).toBe(true)
  })

  it("correctly writes variable-length vectors of bytes", () => {
    let buf = new BufferWriter()
    buf.writeVectorBytes8(arrayToBytes([1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([5, 1, 2, 3, 4, 5]))
    ).toBe(true)

    buf = new BufferWriter()
    buf.writeVectorBytes16(arrayToBytes([1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([0, 5, 1, 2, 3, 4, 5]))
    ).toBe(true)

    buf = new BufferWriter()
    buf.writeVectorBytes24(arrayToBytes([1, 2, 3, 4, 5]))
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([0, 0, 5, 1, 2, 3, 4, 5]))
    ).toBe(true)
  })

  it("correctly writes variable-length vectors using a callback", () => {
    let buf = new BufferWriter()
    buf.writeVector8((buf) => {
      buf.writeUint8(1)
      buf.writeUint8(2)
      buf.writeUint8(3)
      buf.writeUint8(4)
      buf.writeUint8(5)
    })
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([5, 1, 2, 3, 4, 5]))
    ).toBe(true)

    buf = new BufferWriter()
    buf.writeVector16((buf) => {
      buf.writeUint8(1)
      buf.writeUint8(2)
      buf.writeUint8(3)
      buf.writeUint8(4)
      buf.writeUint8(5)
    })
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([0, 5, 1, 2, 3, 4, 5]))
    ).toBe(true)

    buf = new BufferWriter()
    buf.writeVector24((buf) => {
      buf.writeUint8(1)
      buf.writeUint8(2)
      buf.writeUint8(3)
      buf.writeUint8(4)
      buf.writeUint8(5)
    })
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([0, 0, 5, 1, 2, 3, 4, 5]))
    ).toBe(true)
  })

  it("correctly writes nested variable-length vectors using nested callback", () => {
    const buf = new BufferWriter()
    buf.writeVector16((buf) => {
      buf.writeVector8((buf) => {
        buf.writeUint8(1)
        buf.writeUint8(2)
        buf.writeUint8(3)
        buf.writeUint8(4)
        buf.writeUint8(5)
      })
    })
    expect(
      bytesAreEqual(buf.flush(), arrayToBytes([0, 6, 5, 1, 2, 3, 4, 5]))
    ).toBe(true)
  })

  it("errors if a vector write exceeds the maximum size representable in its length field", () => {
    let buf = new BufferWriter()
    buf.writeVectorBytes8(zeros(255))
    expect(() => buf.writeVectorBytes8(zeros(256))).toThrow(TLSError)

    buf = new BufferWriter()
    buf.writeVectorBytes16(zeros(65535))
    expect(() => buf.writeVectorBytes16(zeros(65536))).toThrow(TLSError)

    // Skip the 24-bit test as it requires 16MB allocation

    buf = new BufferWriter()
    expect(() => {
      buf.writeVector8((buf) => {
        buf.writeBytes(zeros(256))
      })
    }).toThrow(TLSError)

    buf = new BufferWriter()
    expect(() => {
      buf.writeVector16((buf) => {
        buf.writeBytes(zeros(65536))
      })
    }).toThrow(TLSError)
  })
})

// Ensure bytesToHex works (used in tests)
describe("bytesToHex", () => {
  it("converts bytes to hex string", () => {
    expect(bytesToHex(arrayToBytes([0, 1, 255]))).toBe("0001ff")
  })
})
