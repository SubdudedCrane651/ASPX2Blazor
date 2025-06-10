import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
from bs4 import BeautifulSoup

# Updated Mapping for ASP.NET Web Forms controls
element_mapping = {
    "asp:Button": {"tag": "button", "attributes": {"Text": "@bind-Value"}, "event": "@onclick"},
    "asp:TextBox": {"tag": "input", "attributes": {"Text": "@bind-Value"}},
    "asp:Label": {"tag": "span", "attributes": {"Text": "@bind-Value"}},
    "asp:DropDownList": {"tag": "select", "attributes": {"SelectedValue": "@bind-Value"}},
    "asp:CheckBox": {"tag": "input", "attributes": {"Checked": "@bind-Value"}, "type": "checkbox"},
    "asp:RadioButton": {"tag": "input", "attributes": {"Checked": "@bind-Value"}, "type": "radio"},
    "asp:HyperLink": {"tag": "a", "attributes": {"NavigateUrl": "href"}},
    "asp:Image": {"tag": "img", "attributes": {"ImageUrl": "src"}},
}

def parse_aspx(file_path):
    """ Reads and parses an ASPX file while removing <form runat='server'> """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            soup = BeautifulSoup(file, "html.parser")  # Using html.parser to preserve casing

            # Remove <form runat="server"> tags but keep content
            for form_tag in soup.find_all("form"):
                if form_tag.has_attr("runat") and form_tag["runat"].lower() == "server":
                    form_tag.unwrap()

            return soup
    except Exception as e:
        messagebox.showerror("Error", f"Failed to parse ASPX file: {e}")
        return None

def parse_cs(file_path):
    """ Extracts event handlers and properties from code-behind (.cs) """
    event_mapping = {}
    class_properties = []

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            code = file.read()

            props = re.findall(r'public (\w+) (\w+);', code)
            for typ, name in props:
                class_properties.append(f"public {typ} {name} {{ get; set; }}")

            events = re.findall(r'protected void (\w+)\(object sender, EventArgs e\)', code)
            for evt in events:
                event_mapping[evt] = f"private void {evt}() {{ /* Converted event logic */ }}"
    except Exception as e:
        messagebox.showerror("Error", f"Error parsing .cs file: {e}")

    return event_mapping, class_properties

def convert_to_blazor(soup, event_mapping):
    """ Converts ASPX elements to Blazor components with correct bindings and events """
    if soup is None:
        return ""

    for element in soup.find_all():
        tag_name = element.name  # Preserve original casing
        if tag_name in element_mapping:
            new_props = element_mapping[tag_name]
            element.name = new_props["tag"]

            # Remove unnecessary ASPX attributes
            element.attrs.pop("runat", None)

            # Convert attributes dynamically
            for attr, replacement in new_props.get("attributes", {}).items():
                if attr in element.attrs:
                    element.attrs[replacement] = element.attrs.pop(attr)

            # Attach event handlers
            if "event" in new_props and "OnClick" in element.attrs:
                event_name = element.attrs.pop("OnClick")
                if event_name in event_mapping:
                    element.attrs[new_props["event"]] = event_name

            # Preserve client-side JavaScript events
            if "OnClientClick" in element.attrs:
                element.attrs["onclick"] = element.attrs.pop("OnClientClick")

            # Add input type if required
            if "type" in new_props:
                element.attrs["type"] = new_props["type"]

    return str(soup)

def save_blazor_file(content, event_mapping, class_props, out_path):
    """ Saves the converted Blazor file including event handlers and properties """
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.write("\n@code {\n")
            f.write("\n".join(class_props))
            f.write("\n")
            f.write("\n".join(event_mapping.values()))
            f.write("\n}")
    except Exception as e:
        messagebox.showerror("Error", f"Could not save .razor file: {e}")

def open_file():
    """ Opens file dialog to process one or multiple ASPX + Code-Behind files """
    paths = filedialog.askopenfilenames(filetypes=[("ASPX Files", "*.aspx")])
    for aspx_path in paths:
        cs_path = aspx_path.replace(".aspx", ".cs")
        events, props = parse_cs(cs_path) if os.path.exists(cs_path) else ({}, [])

        soup = parse_aspx(aspx_path)
        blazor = convert_to_blazor(soup, events)

        razor_path = os.path.splitext(aspx_path)[0] + ".razor"
        save_blazor_file(blazor, events, props, razor_path)

    messagebox.showinfo("Done", f"Converted {len(paths)} file(s) to Blazor!")

# GUI Setup
root = tk.Tk()
root.title("ASPX to Blazor Converter")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack()

tk.Label(frame, text="Select ASPX file(s) to convert:").pack()
tk.Button(frame, text="Convert ASPX", command=open_file).pack()

root.mainloop()