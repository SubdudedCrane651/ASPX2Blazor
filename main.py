import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
from bs4 import BeautifulSoup

# Mapping for ASP.NET controls.
# Keys are the original ASPX control tags.
# Each mapping specifies:
#   - the Blazor tag,
#   - a dictionary mapping ASPX attributes to Blazor ones,
#   - an optional event attribute (e.g. OnClick becomes @onclick).
element_mapping = {
    "asp:Button": {
        "tag": "button",
        "attributes": {"Text": "@bind-Value"},
        "event": "@onclick"
    },
    "asp:TextBox": {
        "tag": "input",
        "attributes": {"Text": "@bind-Value"}
    },
    "asp:Label": {
        "tag": "span",
        "attributes": {"Text": "@bind-Value"}
    },
    "asp:DropDownList": {
        "tag": "select",
        "attributes": {"SelectedValue": "@bind-Value"}
    },
    "asp:CheckBox": {
        "tag": "input",
        "attributes": {"Checked": "@bind-Value"},
        "type": "checkbox"
    },
    "asp:RadioButton": {
        "tag": "input",
        "attributes": {"Checked": "@bind-Value"},
        "type": "radio"
    },
    "asp:HyperLink": {
        "tag": "a",
        "attributes": {"NavigateUrl": "href"}
    },
    "asp:Image": {
        "tag": "img",
        "attributes": {"ImageUrl": "src"}
    }
}

def parse_aspx(path):
    """
    Reads the ASPX file from the given path.
    • Removes any ASPX page directives (lines starting with <%@ ... %>).
    • Creates a BeautifulSoup object (using html.parser, which lowercases tags).
    • Restores known ASP.NET control tags (e.g. asp:Button) from their lowercase versions.
    • Unwraps any <form runat="server"> elements.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        # Remove ASPX directives (e.g. <%@ Page ... %>)
        raw = re.sub(r"<%@.*%>\n?", "", raw)
        soup = BeautifulSoup(raw, "html.parser")
        # Restore ASP.NET control tag names (html.parser lowercases all tags)
        for asp_tag in element_mapping.keys():
            lower_tag = asp_tag.lower()  # e.g., "asp:button"
            for elem in soup.find_all(lower_tag):
                elem.name = asp_tag  # restore original casing (e.g., "asp:Button")
        # Unwrap <form runat="server"> elements (remove tag but keep children)
        for form in soup.find_all("form"):
            if form.get("runat", "").lower() == "server":
                form.unwrap()
        return soup
    except Exception as e:
        messagebox.showerror("Error", f"Failed to parse ASPX file: {e}")
        return None

def parse_cs(path):
    """
    Reads the corresponding code-behind (.cs) file (if it exists) and extracts:
      - Public property declarations of the form: public Type Name;
      - Server event handlers of the form: protected void SomeEvent(object sender, EventArgs e)
    Returns a tuple (events, props):
      • events: A dict mapping event names to an event-stub string.
      • props: A list of property declarations.
    """
    events = {}
    props = []
    if not os.path.exists(path):
        return events, props
    try:
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        # Extract public property declarations (e.g. "public string Foo;")
        for typ, name in re.findall(r"public\s+(\w+)\s+(\w+);", code):
            props.append(f"public {typ} {name} {{ get; set; }}")
        # Extract server event handler names (e.g. "protected void SomeEvent(object sender, EventArgs e)")
        for evt in re.findall(r"protected\s+void\s+(\w+)\(object\s+sender,\s*EventArgs\s+e\)", code):
            events[evt] = f"private void {evt}() {{ /* Converted event logic */ }}"
    except Exception as e:
        messagebox.showerror("Error", f"Error parsing code-behind: {e}")
    return events, props

def convert_to_blazor(soup, events, class_props):
    """
    Traverses the BeautifulSoup object and converts ASPX controls into Blazor-compatible HTML.
    For each ASP.NET control:
      - Replaces its tag with the Blazor equivalent.
      - Maps attributes (e.g. "Text" is replaced with "@bind-Value").
      - For each binding, adds a property declaration if not already defined.
      - Processes the onclick attribute: if its value is a valid C# identifier that exists in events,
        it maps the attribute to Blazor's event binding (e.g. @onclick) and removes the original onclick.
      - Leaves client-side JavaScript intact.
    Returns the converted HTML as a string.
    """
    # Collect names from already-declared properties to avoid duplication.
    seen_props = set()
    for p in class_props:
        m = re.match(r"public\s+\w+\s+(\w+)", p)
        if m:
            seen_props.add(m.group(1))

    for elm in soup.find_all():
        tag = elm.name
        if tag in element_mapping:
            mapping = element_mapping[tag]
            # Replace ASP.NET control tag with Blazor equivalent.
            elm.name = mapping["tag"]
            # Remove ASP.NET-specific attributes.
            if "runat" in elm.attrs:
                del elm.attrs["runat"]
            # Set type attribute if defined (e.g. for input controls).
            if "type" in mapping:
                elm.attrs["type"] = mapping["type"]
            # Process attribute mappings.
            for asp_attr, target_attr in mapping.get("attributes", {}).items():
                key_lower = asp_attr.lower()  # html.parser lowercases attribute names.
                if key_lower in elm.attrs:
                    val = elm.attrs.pop(key_lower)
                    elm.attrs[target_attr] = val
                    # Add a binding property if not already declared.
                    if target_attr.startswith("@bind") and val not in seen_props:
                        class_props.append(f"public string {val} {{ get; set; }}")
                        seen_props.add(val)
            # Process event mapping for onclick.
            if "onclick" in elm.attrs:
                candidate = elm.attrs["onclick"].strip()
                # If candidate is a valid C# identifier and exists in events, map it.
                if re.fullmatch(r"[A-Za-z_]\w*", candidate) and candidate in events:
                    elm.attrs[mapping["event"]] = candidate
                    del elm.attrs["onclick"]
            # Map onclientclick to onclick (preserving client-side JS)
            if "onclientclick" in elm.attrs:
                elm.attrs["onclick"] = elm.attrs.pop("onclientclick")
    return str(soup)

def save_blazor_file(content, events, props, out_path, route):
    """
    Saves the converted content into a .razor file.
    Prepends a dynamic preamble:
      - The @page directive is generated using the given route.
      - Other directives (@using, @inject) are added.
    Appends an @code block containing the property declarations and event stubs.
    """
    preamble = (
        f"@page \"{route}\"\n"
        "@using Home\n"
        "@inject IJSRuntime JS\n\n"
    )
    code_block = "\n@code {\n"
    if props:
        code_block += "\n".join(props) + "\n"
    if events:
        code_block += "\n".join(events.values()) + "\n"
    code_block += "}\n"

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(preamble)
            f.write(content)
            f.write("\n")
            f.write(code_block)
    except Exception as e:
        messagebox.showerror("Error", f"Could not save file: {e}")

def open_file():
    """
    Opens a file dialog for selecting one or more ASPX files.
    For each selected file:
      - Parses the ASPX file and its corresponding code-behind (if available),
      - Converts the ASPX content into Blazor format,
      - Dynamically sets the route based on the filename (e.g. "/MyPage" for "MyPage.aspx"),
      - Saves the output as a .razor file in the same folder.
    """
    files = filedialog.askopenfilenames(filetypes=[("ASPX Files", "*.aspx")])
    for asp_path in files:
        cs_path = asp_path.replace(".aspx", "aspx.cs")
        events, props = parse_cs(cs_path)
        soup = parse_aspx(asp_path)
        if soup is None:
            continue
        converted_html = convert_to_blazor(soup, events, props)
        base_name = os.path.splitext(os.path.basename(asp_path))[0]
        route = f"/{base_name}"
        razor_path = os.path.splitext(asp_path)[0] + ".razor"
        save_blazor_file(converted_html, events, props, razor_path, route)
    messagebox.showinfo("Done", f"Converted {len(files)} file(s) to Blazor!")

# --- GUI Setup ---
root = tk.Tk()
root.title("ASPX to Blazor Converter")
frame = tk.Frame(root, padx=20, pady=20)
frame.pack()
tk.Label(frame, text="Select ASPX file(s) to convert:").pack()
tk.Button(frame, text="Convert", command=open_file).pack()
root.mainloop()