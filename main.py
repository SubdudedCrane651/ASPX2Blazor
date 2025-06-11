import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
from bs4 import BeautifulSoup

# Mapping ASP.NET controls to Blazor components
element_mapping = {
    "asp:Button": {"tag": "button", "attributes": {"OnClick": "@onclick"}, "event": "@onclick"},
    "asp:TextBox": {"tag": "input"},
    "asp:Label": {"tag": "span"},
    "asp:DropDownList": {"tag": "select"},
    "asp:CheckBox": {"tag": "input", "attributes": {"Checked": "@onclick"}, "type": "checkbox"},
    "asp:RadioButton": {"tag": "input", "attributes": {"Checked": "@onclick"}, "type": "radio"},
    "asp:HyperLink": {"tag": "a", "attributes": {"NavigateUrl": "href"}},
    "asp:Image": {"tag": "img", "attributes": {"ImageUrl": "src"}},
}

def parse_aspx(path):
    """Reads ASPX file, removes directives, restores ASP.NET tag names, and removes runat="server"."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        
        # Remove ASPX directives (e.g., <%@ Page ... %>)
        raw = re.sub(r"<%@.*%>\n?", "", raw)
        
        soup = BeautifulSoup(raw, "html.parser")

        # Restore ASP.NET control tag names
        for asp_tag in element_mapping:
            for elem in soup.find_all(asp_tag.lower()):
                elem.name = asp_tag

        # Remove runat="server" attributes from all tags
        for elem in soup.find_all():
            if "runat" in elem.attrs:
                del elem.attrs["runat"]

        return soup
    except Exception as e:
        messagebox.showerror("Error", f"Failed to parse ASPX file: {e}")
        return None

def parse_cs(path):
    """Extracts properties and event handlers from code-behind (.cs) files."""
    events, props = {}, []
    if not os.path.exists(path):
        return events, props
    try:
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        props = [f"public {typ} {name} {{ get; set; }}" for typ, name in re.findall(r"public\s+(\w+)\s+(\w+);", code)]
        events = {evt: f"private void {evt}() {{ /* Converted event logic */ }}" for evt in re.findall(r"protected\s+void\s+(\w+)\(object sender,\s*EventArgs e\)", code)}
    except Exception as e:
        messagebox.showerror("Error", f"Error parsing code-behind: {e}")
    return events, props

def convert_to_blazor(soup, events, class_props):
    """Converts ASPX controls into Blazor components and generates event methods."""
    seen_props = {m.group(1) for p in class_props if (m := re.match(r"public\s+\w+\s+(\w+)", p))}
    unique_events = set()

    for elm in soup.find_all():
        if elm.name in element_mapping:
            mapping = element_mapping[elm.name]
            elm.name = mapping["tag"]
            if "type" in mapping:
                elm.attrs["type"] = mapping["type"]
            for asp_attr, blz_attr in mapping.get("attributes", {}).items():
                if asp_attr.lower() in elm.attrs:
                    val = elm.attrs.pop(asp_attr.lower())
                    elm.attrs[blz_attr] = val
                    if blz_attr.startswith("@onclick") and val not in seen_props:
                        #class_props.append(f"public string {val} {{ get; set; }}")
                        unique_events.add(val)
                        seen_props.add(val)
            # if "onclick" in elm.attrs:
            #     raw = elm.attrs["onclick"].strip()
            #     if re.fullmatch(r"[A-Za-z_]\w*", raw):
            #         elm.attrs[mapping.get("event", "@onclick")] = raw
            #         unique_events.add(raw)
            #         del elm.attrs["onclick"]
            if "onclientclick" in elm.attrs:
                elm.attrs["onclick"] = elm.attrs.pop("onclientclick")
            if "text" in elm.attrs:
                elm.string = elm.attrs.pop("text")
   

    return str(soup), unique_events

def save_blazor_file(content, events, props, out_path, route, unique_events):
    """Saves converted ASPX content into a .razor file with event-based @code generation."""
    preamble = f"""@page "{route}"
@inject IJSRuntime JS

"""
    code_block = "\n@code {\n"

    # Generate private void functions for each unique @onclick event
    for event_name in unique_events:
        code_block += f"    private void {event_name}()\n    {{\n        // Event handler for {event_name}\n    }}\n\n"

    if props:
        code_block += "    " + "\n    ".join(props) + "\n"
    if events:
        code_block += "    " + "\n    ".join(events.values()) + "\n"
    code_block += "}\n"

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(preamble)
            f.write(content)
            f.write(code_block)
    except Exception as e:
        messagebox.showerror("Error", f"Could not save .razor file: {e}")

def open_file():
    """Opens a file dialog for selecting ASPX files and generates corresponding .razor files."""
    files = filedialog.askopenfilenames(filetypes=[("ASPX Files", "*.aspx")])
    for asp_path in files:
        cs_path = asp_path.replace(".aspx", ".cs")
        events, props = parse_cs(cs_path)
        soup = parse_aspx(asp_path)
        if not soup:
            continue
        html, unique_events = convert_to_blazor(soup, events, props)
        folder = os.path.dirname(asp_path)
        base = os.path.splitext(os.path.basename(asp_path))[0]
        cap_base = base[0].upper() + base[1:]
        out_file = os.path.join(folder, cap_base + ".razor")
        save_blazor_file(html, events, props, out_file, f"/{cap_base}", unique_events)
    messagebox.showinfo("Done", "All selected files converted!")

# GUI Setup
root = tk.Tk()
root.title("ASPX to Blazor Converter")
frame = tk.Frame(root, padx=20, pady=20)
frame.pack()
tk.Label(frame, text="Select ASPX file(s) to convert:").pack(pady=(0,5))
tk.Button(frame, text="Convert to Blazor", command=open_file).pack()
root.mainloop()