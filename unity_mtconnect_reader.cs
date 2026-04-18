using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using UnityEngine.Networking;
using System.Xml.Linq; 
using System.Linq;

public class unity_mtconnect_reader : MonoBehaviour
{
    [Header("Network Settings")]
    public string piIP = "192.168.1.94"; 
    public string port = "5001";
    public float pollRate = 0.05f; // Increased to 20Hz for smoother tracking

    [Header("Smoothing (Physics)")]
    [Tooltip("Lower = snappier/more lag. Higher = smoother/more delay.")]
    public float smoothTime = 0.15f; 
    
    [Header("Component Transforms")]
    public Transform toolhead; 
    public Transform gantry;   
    public Transform bed;      

    [Header("Live Data (MM)")]
    public float liveX; 
    public float liveY; 
    public float liveZ; 

    // Internal physics variables for SmoothDamp
    private Vector3 startToolPos, startGantryPos, startBedPos;
    private Vector3 xVelocity, yVelocity, zVelocity;

    void Start()
    {
        // Capture initial CAD positions as our "Zero" reference
        if(toolhead) startToolPos = toolhead.localPosition;
        if(gantry) startGantryPos = gantry.localPosition;
        if(bed) startBedPos = bed.localPosition;

        StartCoroutine(PollMTConnect());
    }

    IEnumerator PollMTConnect()
    {
        string url = $"http://{piIP}:{port}/current";
        
        while (true)
        {
            using (UnityWebRequest webRequest = UnityWebRequest.Get(url))
            {
                // Set a short timeout so a lost packet doesn't freeze the script
                webRequest.timeout = 1; 
                yield return webRequest.SendWebRequest();

                if (webRequest.result == UnityWebRequest.Result.Success)
                {
                    ParseMTConnectXML(webRequest.downloadHandler.text);
                }
            }
            yield return new WaitForSeconds(pollRate);
        }
    }

    void ParseMTConnectXML(string xmlData)
    {
        try 
        {
            XDocument doc = XDocument.Parse(xmlData);
            
            // Extract all data items from the stream
            var samples = doc.Descendants().Where(d => d.Attribute("dataItemId") != null);
            
            foreach (var s in samples)
            {
                string id = s.Attribute("dataItemId").Value;
                string rawValue = s.Value;

                // Guard against un-homed axes
                if (rawValue == "UNAVAILABLE") continue;

                if (float.TryParse(rawValue, out float val))
                {
                    // Map to the specific IDs from your Sovol Device.xml
                    if (id == "x_pos") liveX = val;
                    if (id == "y_pos") liveY = val;
                    if (id == "z_pos") liveZ = val;
                }
            }
        }
        catch (System.Exception e) 
        { 
            Debug.LogWarning("MTConnect Parse Error: " + e.Message); 
        }
    }

    // Move logic happens in Update so the smoothing is independent of the network speed
    void Update()
    {
        if (!toolhead || !gantry || !bed) return;

        // 1. Clamp values to the Sovol Ace build volume (220x220x250)
        float cX = Mathf.Clamp(liveX, 0, 220);
        float cY = Mathf.Clamp(liveY, 0, 220);
        float cZ = Mathf.Clamp(liveZ, 0, 252);

        // 2. Calculate Target Positions (Converting mm to Unity meters)
        // Adjust the +/- signs here if an axis moves the "wrong" way
        float targetX = startToolPos.x - (cX / 1000f); 
        float targetY = startBedPos.y - (cY / 1000f); 
        float targetZ = startGantryPos.z + (cZ / 1000f);

        // 3. Apply SmoothDamp 
        // This calculates the velocity needed to reach the target smoothly
        toolhead.localPosition = Vector3.SmoothDamp(
            toolhead.localPosition, 
            new Vector3(targetX, startToolPos.y, startToolPos.z), 
            ref xVelocity, 
            smoothTime
        );

        gantry.localPosition = Vector3.SmoothDamp(
            gantry.localPosition, 
            new Vector3(startGantryPos.x, startGantryPos.y, targetZ), 
            ref zVelocity, 
            smoothTime
        );

        bed.localPosition = Vector3.SmoothDamp(
            bed.localPosition, 
            new Vector3(startBedPos.x, targetY, startBedPos.z), 
            ref yVelocity, 
            smoothTime
        );
    }
}