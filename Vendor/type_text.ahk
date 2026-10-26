; type_text.ahk — typing engine for iTeroToolBox's hotkeys.
;
; Why this exists at all: hand-rolled SendInput calls from Python (ctypes)
; type reliably on the local machine but drop/duplicate characters once a
; remote-control session (TeamViewer, controlling a customer's machine) is
; in the loop — most visibly the space character, gluing words together.
; AutoHotkey's own Send engine — built on the exact same Win32 SendInput()
; API, refined over ~20 years specifically against cases like this — does
; not have that problem. Delegating the actual typing to a real AutoHotkey
; interpreter, rather than reimplementing its behavior, is the point of
; this script.
;
; (SendPlay — the journal-hook based mode — was considered first, but
; AutoHotkey's own docs mark it unreliable with UAC enabled and possibly
; non-functional on Windows 11 at all, which is exactly this app's target
; environment. SendInput, the default mode below, is what's actually in
; play whenever "AutoHotkey just types reliably" is observed in practice.)
;
; Usage: AutoHotkey64.exe type_text.ahk "<path to a UTF-8 text file>"
; The text file's content is what gets typed — kept out of the script
; source entirely (no inline text, no escaping to get right) since a
; hotkey's text can contain quotes, backticks, or anything else that
; would otherwise have to be safely embedded in AHK syntax.

#Requires AutoHotkey v2.0
#SingleInstance Force
SendMode "Input"
SetKeyDelay -1, -1

if (A_Args.Length < 1) {
    ExitApp 1
}

textPath := A_Args[1]
content := FileRead(textPath, "UTF-8")

; Normalize all line-ending styles to a plain "`n" so the split below
; doesn't leave stray "`r" characters or blank lines behind.
content := StrReplace(content, "`r`n", "`n")
content := StrReplace(content, "`r", "`n")
lines := StrSplit(content, "`n")

Loop lines.Length {
    line := lines[A_Index]
    if (line != "")
        SendText(line)
    ; A newline in the source text becomes a real Enter keystroke —
    ; SendText has no way to "type" a bare line-feed character itself.
    if (A_Index < lines.Length)
        Send("{Enter}")
}

ExitApp
