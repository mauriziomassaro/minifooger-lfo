const int lfoPin = 3;
const int green = 5;
const int red = 6;
const int ratePin = A0;
const int depthPin = A1;
const int triPin = 10;
const int sawPin = 11;
const int offPin = 12;
volatile bool off;
volatile float triRate;
volatile float triDepth;
volatile float sendCV;
volatile float randV;
volatile float lfoDiv;
volatile float dt;

void setup()
{
  Serial.begin(9600);
  pinMode (triPin, INPUT);
  pinMode (sawPin, INPUT);
  pinMode (lfoPin, OUTPUT);
  pinMode (green, OUTPUT);
  pinMode (red, OUTPUT);
  attachInterrupt(digitalPinToInterrupt(offPin), offMode, LOW);
  interrupts();
}

void loop()
{
              if (digitalRead(triPin) == LOW && digitalRead(sawPin) == LOW) {
                     digitalWrite(red, LOW);
                     lfoDiv = map(analogRead(depthPin), 0, 1023, 1, 255);
                     dt = map(analogRead(ratePin), 0, 1023, 1, 1023);
                     randV = random(0, 255);
                     sendCV = randV / lfoDiv;
                     Serial.println(sendCV);
                     analogWrite(lfoPin, sendCV);
                     digitalWrite(green, HIGH);
                     delay(dt);
                     digitalWrite(green,LOW);
                     delay(dt);
                      }
              if (digitalRead(triPin) == HIGH) {
                     digitalWrite(green, LOW);
                     triDepth = map(analogRead(depthPin), 0, 1023, 1, 100);
                     triRate = map(analogRead(ratePin), 0, 1023, 32, 1); 
                      //Triangular wave
                          for(float i=0;i<=255;i=i+(triRate))
                          {
                            sendCV = (i / triDepth);
                            Serial.println(sendCV);
                            analogWrite(lfoPin, sendCV);
                            digitalWrite(red, LOW);
                            delay(2);
                          }
                          for(float i=255;i>=0;i=i-(triRate))
                          {
                            sendCV = (i / triDepth);
                            Serial.println(sendCV);
                            analogWrite(lfoPin, sendCV);
                            digitalWrite(red,HIGH);
                            delay (2);
                          } 
              }
              if (digitalRead(sawPin) == HIGH) {
                     digitalWrite(green, LOW);
                     triDepth = map(analogRead(depthPin), 0, 1023, 1, 100);
                     triRate = map(analogRead(ratePin), 0, 1023, 16, 1);
                      //Ramp Down wave
                          for(float i=255;i>=0;i=i-(triRate))
                          {
                            sendCV = (i / triDepth);
                            Serial.println(sendCV);
                            analogWrite(lfoPin, sendCV);
                            digitalWrite(red, HIGH);
                            delay(2);
                          } 
              }
}

void offMode() {
              off = true; 
             // sendCV = 0;
             // analogWrite(lfoPin, sendCV);
              digitalWrite(red, LOW);
              digitalWrite(green, LOW);
}
