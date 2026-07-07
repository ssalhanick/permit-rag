package com.scottsalhanick.permitrag.roomcapture;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.JSObject;

@CapacitorPlugin(name = "RoomCapture")
public class RoomCapturePlugin extends Plugin {

    @PluginMethod
    public void isAvailable(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("available", false);
        call.resolve(ret);
    }

    @PluginMethod
    public void startCapture(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("schema_version", "1.0");
        ret.put("room_label", call.getString("room_label", "room"));
        ret.put("units", "meters");
        ret.put("error", "ARCore room semantics not yet implemented — use manual fallback.");
        call.resolve(ret);
    }
}
