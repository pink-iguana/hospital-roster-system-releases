import AppKit
import ApplicationServices
import Foundation

func fail(_ message: String) -> Never {
    fputs(message + "\n", stderr)
    exit(1)
}
guard AXIsProcessTrusted() else { fail("Accessibility permission is unavailable") }
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "preflight" {
    print("Accessibility preflight passed")
    exit(0)
}
guard CommandLine.arguments.count == 2, let pid = Int32(CommandLine.arguments[1]) else {
    fail("Expected application PID or preflight")
}
let app = AXUIElementCreateApplication(pid)
func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else {
        return nil
    }
    return result
}
func elements(_ element: AXUIElement, depth: Int = 0) -> [AXUIElement] {
    if depth > 25 { return [] }
    let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
    return [element] + children.flatMap { elements($0, depth: depth + 1) }
}
func find(_ title: String) -> AXUIElement? {
    return elements(app).first {
        let name = (attribute($0, kAXTitleAttribute) as? String) ??
                   (attribute($0, kAXDescriptionAttribute) as? String) ?? ""
        let role = attribute($0, kAXRoleAttribute) as? String ?? ""
        return name == title && ["AXRadioButton", "AXButton", "AXTab"].contains(role)
    }
}
NSRunningApplication(processIdentifier: pid)?.activate(options: [.activateIgnoringOtherApps])
var records: [[String: Any]] = []
for title in ["Roster", "Preferences"] {
    let deadline = Date().addingTimeInterval(60)
    var control: AXUIElement?
    while control == nil && Date() < deadline {
        control = find(title)
        if control == nil { Thread.sleep(forTimeInterval: 0.3) }
    }
    guard let tab = control else { fail("GUI tab not found: " + title) }
    guard AXUIElementPerformAction(tab, kAXPressAction as CFString) == .success else {
        fail("Cannot press GUI tab: " + title)
    }
    var selected = false
    let selectionDeadline = Date().addingTimeInterval(10)
    while !selected && Date() < selectionDeadline {
        let value = attribute(tab, kAXValueAttribute) as? NSNumber
        selected = value?.boolValue == true
        if !selected { Thread.sleep(forTimeInterval: 0.2) }
    }
    guard selected else { fail("GUI tab selection was not confirmed: " + title) }
    records.append(["tab": title, "selected": true])
}
let data = try JSONSerialization.data(withJSONObject: records, options: [.prettyPrinted])
print(String(data: data, encoding: .utf8)!)
