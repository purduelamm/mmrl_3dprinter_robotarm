using UnityEngine;
using System.Collections;

public class move_testscript : MonoBehaviour
{
    [Header("Component Transforms")]
    public Transform toolhead; 
    public Transform gantry;   
    public Transform bed;      

    [Header("Printer Target (MM)")]
    public float targetX; 
    public float targetY; 
    public float targetZ; 

    [Header("Settings")]
    public float travelTime = 2.0f;
    
    private Vector3 startToolPos;
    private Vector3 startGantryPos;
    private Vector3 startBedPos;

    void Start()
    {
        startToolPos = toolhead.localPosition;
        startGantryPos = gantry.localPosition;
        startBedPos = bed.localPosition;
    }

    void Update()
    {
        // Still works if you click the Game View and press Enter
        if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))
        {
            ExecuteMove();
        }
    }

    // This adds a "Move Printer" option when you right-click the script name
    [ContextMenu("Move Printer")]
    public void ExecuteMove()
    {
        if (!Application.isPlaying) return; // Only works while game is running
        
        StopAllCoroutines();
        
        float clampedX = Mathf.Clamp(targetX, 0, 220);
        float clampedY = Mathf.Clamp(targetY, 0, 200);
        float clampedZ = Mathf.Clamp(targetZ, 0, 252);

        StartCoroutine(MoveToAbsolute(clampedX, clampedY, clampedZ));
    }

    IEnumerator MoveToAbsolute(float xMM, float yMM, float zMM)
    {
        float elapsed = 0;
        float currentToolX = toolhead.localPosition.x;
        float currentGantryZ = gantry.localPosition.z;
        float currentBedY = bed.localPosition.y;

        float finalToolX = startToolPos.x - (xMM / 1000f);
        float finalGantryZ = startGantryPos.z + (zMM / 1000f);
        float finalBedY = startBedPos.y - (yMM / 1000f);

        while (elapsed < travelTime)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.SmoothStep(0, 1, elapsed / travelTime);

            toolhead.localPosition = new Vector3(Mathf.Lerp(currentToolX, finalToolX, t), startToolPos.y, startToolPos.z);
            gantry.localPosition = new Vector3(startGantryPos.x, startGantryPos.y, Mathf.Lerp(currentGantryZ, finalGantryZ, t));
            bed.localPosition = new Vector3(startBedPos.x, Mathf.Lerp(currentBedY, finalBedY, t), startBedPos.z);

            yield return null;
        }
    }
}